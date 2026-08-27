#!/usr/bin/env python3
"""
ADios blocklist builder.

Reads lists, blacklist, whitelist, and probe_cache from this directory (config/).
Writes hosts, pihole-hosts, dnscrypt-hosts, and adguardhosts.txt at the repository root.

Pipeline: merge sources (track origin) → dedupe/sort → unfiltered DNS probe + WHOIS
→ probe_cache → whitelist → dead filter → write outputs.

DNS probe uses explicitly unfiltered public DoH resolvers (never Google/Cloudflare,
never your LAN). Optional env:
  SKIP_DNS_CHECK=1        skip probing (fast local build)
  DNS_WORKERS=64          parallel probes
  DNS_MAX_PROBE=25000     max domains checked per run
  VERIFIED_TTL_DAYS=30    re-check alive entries after this many days
  DEAD_RECHECK_DAYS=90    re-check first dead mark once; second dead → permanent
  DNS_PROBE_ENDPOINTS=    comma-separated DoH base URLs (overrides defaults)

Runtime: Python 3.9+ only — standard library, no pip, no requirements.txt.
On a clean VPS/PC: clone the repo, then:
  python3 config/build_hosts.py
"""

from __future__ import annotations

import json
import os
import random
import re
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

# Bundled dependency spec (used only if non-empty). Default: stdlib-only, nothing to install.
REQUIREMENTS: tuple[str, ...] = ()
MIN_PYTHON = (3, 9)

CONFIG = Path(__file__).resolve().parent
ROOT = CONFIG.parent
LISTS_FILE = CONFIG / "lists"
BLACKLIST_FILE = CONFIG / "blacklist"
WHITELIST_FILE = CONFIG / "whitelist"
DEAD_FILE = CONFIG / "dead"
PROBE_CACHE_FILE = CONFIG / "probe_cache"
VERIFIED_FILE = CONFIG / "verified"  # legacy; migrated into probe_cache

BLACKLIST_SOURCE = "config/blacklist"

# Explicitly unfiltered public DoH resolvers (no Google, no Cloudflare).
DEFAULT_DNS_RESOLVERS: tuple[tuple[str, str], ...] = (
    ("Public RDNS Open", "https://open.public-rdns.com/dns-query"),
    ("dnsHome.de", "https://dns.dnshome.de/dns-query"),
    ("Control D Unfiltered", "https://freedns.controld.com/p0"),
    ("dnswarden Uncensored", "https://doh.us.dnswarden.com/uncensored"),
)

OUTPUT_PIHOLE = ROOT / "pihole-hosts"
OUTPUT_HOSTS = ROOT / "hosts"
OUTPUT_DNSCRYPT = ROOT / "dnscrypt-hosts"
OUTPUT_ADGUARD = ROOT / "adguardhosts.txt"

REQUEST_HEADERS = {
    "User-Agent": "ADios-build-hosts/2.0 (+https://github.com/AlexRabbit/ADios)",
}

ProbeStatus = Literal["alive", "dead", "dead_permanent"]
ProbeResult = Literal["alive", "dead", "inconclusive"]

_VALID_HOST = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_LEADING_JUNK = re.compile(r"^[\s\|\@\*\-\.]+")
_TRAILING_JUNK = re.compile(r"[\s\|\^\*\-\.]+$")
_EXTENSION_TAIL = re.compile(r"\.(js|html|css|php|json|xml|txt|woff2?)$")
_GLUED_TLD = re.compile(r"(com|net|org|edu|gov|co|io|uk|de|fr)(?=[a-z0-9])")
_INVALID_TLDS = frozenset(
    {
        "js",
        "html",
        "css",
        "php",
        "json",
        "xml",
        "txt",
        "png",
        "gif",
        "jpg",
        "jpeg",
        "woff",
        "woff2",
        "svg",
        "ico",
        "map",
        "exe",
        "dll",
    }
)

SKIP_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "local",
        "broadcasthost",
        "ip6-localhost",
        "ip6-loopback",
    }
)

DNS_TYPE_A = 1
DNS_TYPE_AAAA = 28
NXDOMAIN_RCODE = 3
MIN_NXDOMAIN_CONSENSUS = 2


def ensure_runtime() -> None:
    """Verify Python version and install bundled REQUIREMENTS if any are declared."""
    if sys.version_info < MIN_PYTHON:
        need = ".".join(str(n) for n in MIN_PYTHON)
        print(f"Error: Python {need}+ required (found {sys.version.split()[0]})", file=sys.stderr)
        sys.exit(1)

    if not REQUIREMENTS:
        return

    missing: list[str] = []
    for spec in REQUIREMENTS:
        pkg = re.split(r"[<>=!~\s]", spec, maxsplit=1)[0].replace("-", "_")
        try:
            __import__(pkg)
        except ImportError:
            missing.append(spec)

    if not missing:
        return

    print(f"Installing bundled dependencies: {', '.join(missing)}")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing],
    )


def _strip_inline_comment(line: str) -> str | None:
    s = line.strip()
    if not s:
        return None
    if s.startswith("!"):
        return None
    if s.startswith("#"):
        return None
    if "//" in s and not s.startswith("http"):
        s = s.split("//", 1)[0].strip()
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    return s or None


def _is_ip_address(token: str) -> bool:
    token = token.strip().lower()
    if not token:
        return False
    if token.startswith("[") and token.endswith("]"):
        token = token[1:-1]
    if ":" in token:
        return True
    parts = token.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def purify_hostname(raw: str) -> str | None:
    line = _strip_inline_comment(raw)
    if not line:
        return None

    line = line.strip().lower()
    if not line:
        return None

    if line.startswith("@@"):
        return None

    if line.startswith(("[", "/", "regex:", "regexp:")):
        return None

    parts = line.split()
    if len(parts) >= 2 and _is_ip_address(parts[0]):
        line = parts[1]
    elif len(parts) == 1:
        line = parts[0]
    else:
        line = parts[-1]

    for prefix in ("@@||", "||", "|http", "|https"):
        if line.startswith(prefix):
            line = line[len(prefix) :]
            break
    line = line.lstrip("@|")

    if "://" in line:
        from urllib.parse import urlparse

        parsed = urlparse(line)
        line = (parsed.hostname or "").lower()
    elif line.startswith("//"):
        from urllib.parse import urlparse

        parsed = urlparse("https:" + line)
        line = (parsed.hostname or "").lower()

    if not line:
        return None

    line = line.split("/")[0].split("?")[0].split("#")[0]
    if ":" in line and not line.startswith("["):
        host_part, _, port = line.rpartition(":")
        if port.isdigit():
            line = host_part

    if line.startswith("*."):
        line = line[2:]
    elif line.startswith("*") and len(line) > 1:
        line = line[1:]

    for _ in range(8):
        prev = line
        line = _LEADING_JUNK.sub("", line)
        line = _TRAILING_JUNK.sub("", line)
        line = line.strip(".-")
        if line == prev:
            break

    if line.endswith("^"):
        line = line[:-1].rstrip(".-|")

    if not line or line in SKIP_NAMES:
        return None

    if line.startswith("www."):
        line = line[4:]

    if _is_ip_address(line):
        return None

    if "." not in line:
        return None

    if _EXTENSION_TAIL.search(line) and line.count(".") <= 2:
        return None

    labels = line.split(".")
    if labels[-1] in _INVALID_TLDS:
        return None
    if len(labels) > 12:
        return None
    if any(len(label) > 63 for label in labels):
        return None
    if sum(1 for label in labels if label.isdigit()) >= max(2, len(labels) - 1):
        return None
    if any(_GLUED_TLD.search(label) for label in labels[:-1]):
        return None

    if not _VALID_HOST.match(line):
        return None

    if len(line) > 253:
        return None

    return line


def hosts_from_line(raw: str) -> list[str]:
    line = _strip_inline_comment(raw)
    if not line:
        return []

    parts = line.strip().lower().split()
    if len(parts) >= 2 and _is_ip_address(parts[0]):
        out: list[str] = []
        for token in parts[1:]:
            host = purify_hostname(token)
            if host:
                out.append(host)
        return out

    host = purify_hostname(line)
    return [host] if host else []


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        print(f"Warning: missing file {path}", file=sys.stderr)
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def fetch_list(url: str) -> list[str]:
    try:
        request = Request(url, headers=REQUEST_HEADERS)
        with urlopen(request, timeout=60) as response:
            if response.status and response.status >= 400:
                raise HTTPError(url, response.status, response.reason, response.headers, None)
            body = response.read()
        return body.decode("utf-8", errors="replace").splitlines()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Error fetching {url}: {exc}", file=sys.stderr)
        return []


def load_url_sources() -> list[str]:
    lines = read_lines(LISTS_FILE)
    return [u.strip() for u in lines if u.strip() and not u.strip().startswith("#")]


def collect_hosts_with_source(
    lines: list[str],
    source: str,
    bucket: set[str],
    sources: dict[str, str],
) -> None:
    for raw in lines:
        for host in hosts_from_line(raw):
            bucket.add(host)
            if host not in sources:
                sources[host] = source


def load_host_set(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in read_lines(path):
        for host in hosts_from_line(raw):
            names.add(host)
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            host = purify_hostname(stripped)
            if host:
                names.add(host)
    return names


def save_host_set(path: Path, names: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(sorted(names))
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


def load_whitelist() -> set[str]:
    return load_host_set(WHITELIST_FILE)


def _name_cmp(domain: str) -> str:
    parts = domain.split(".")
    parts.reverse()
    return ".".join(parts)


def _encode_dns_name(domain: str) -> bytes:
    out = bytearray()
    for label in domain.rstrip(".").split("."):
        encoded = label.encode("ascii", errors="ignore")
        if len(encoded) > 63:
            raise ValueError(f"label too long: {label}")
        out.append(len(encoded))
        out.extend(encoded)
    out.append(0)
    return bytes(out)


def _build_wire_query(domain: str, qtype: int) -> bytes:
    query_id = random.randint(0, 0xFFFF)
    header = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
    question = _encode_dns_name(domain) + struct.pack("!HH", qtype, 1)
    return header + question


def _parse_wire_response(data: bytes) -> tuple[int, int]:
    """Return (rcode, answer_count). rcode -1 on parse failure."""
    if len(data) < 12:
        return -1, 0
    _qid, flags, _qd, ancount, _ns, _ar = struct.unpack("!HHHHHH", data[:12])
    rcode = flags & 0xF
    return rcode, ancount


def _load_dns_resolvers() -> tuple[tuple[str, str], ...]:
    override = os.environ.get("DNS_PROBE_ENDPOINTS", "").strip()
    if not override:
        return DEFAULT_DNS_RESOLVERS
    resolvers: list[tuple[str, str]] = []
    for idx, endpoint in enumerate(override.split(","), start=1):
        endpoint = endpoint.strip()
        if endpoint:
            resolvers.append((f"custom-{idx}", endpoint))
    return tuple(resolvers) if resolvers else DEFAULT_DNS_RESOLVERS


def _doh_query_wire(endpoint: str, domain: str, qtype: int) -> tuple[int | None, bool]:
    wire = _build_wire_query(domain, qtype)
    headers = {
        **REQUEST_HEADERS,
        "Content-Type": "application/dns-message",
        "Accept": "application/dns-message",
    }
    try:
        request = Request(endpoint, data=wire, headers=headers, method="POST")
        with urlopen(request, timeout=12) as response:
            payload = response.read()
        rcode, ancount = _parse_wire_response(payload)
        if rcode < 0:
            return None, False
        return rcode, ancount > 0
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None, False


def _doh_query(endpoint: str, domain: str, rtype: int) -> tuple[int | None, bool]:
    """Query one DoH resolver. Tries RFC 8484 wire POST."""
    return _doh_query_wire(endpoint, domain, rtype)


def _dns_resolvers() -> tuple[tuple[str, str], ...]:
    if not hasattr(_dns_resolvers, "_cached"):
        _dns_resolvers._cached = _load_dns_resolvers()  # type: ignore[attr-defined]
    return _dns_resolvers._cached  # type: ignore[attr-defined]


def _dns_nxdomain_consensus(domain: str) -> ProbeResult:
    """
    Query all unfiltered resolvers. alive = any answer; dead = NXDOMAIN consensus;
    inconclusive = split/timeout (keep domain).
    """
    resolvers = _dns_resolvers()
    any_answer = False
    a_nxdomain = 0
    aaaa_nxdomain = 0
    a_responses = 0
    aaaa_responses = 0

    for _name, endpoint in resolvers:
        status, has_answer = _doh_query(endpoint, domain, DNS_TYPE_A)
        if status is not None:
            a_responses += 1
            if has_answer:
                any_answer = True
            elif status == NXDOMAIN_RCODE:
                a_nxdomain += 1

        status, has_answer = _doh_query(endpoint, domain, DNS_TYPE_AAAA)
        if status is not None:
            aaaa_responses += 1
            if has_answer:
                any_answer = True
            elif status == NXDOMAIN_RCODE:
                aaaa_nxdomain += 1

    if any_answer:
        return "alive"

    if (
        a_nxdomain >= MIN_NXDOMAIN_CONSENSUS
        and aaaa_nxdomain >= MIN_NXDOMAIN_CONSENSUS
        and a_responses >= MIN_NXDOMAIN_CONSENSUS
        and aaaa_responses >= MIN_NXDOMAIN_CONSENSUS
    ):
        return "dead"

    return "inconclusive"


def _rdap_domain_unregistered(domain: str) -> bool | None:
    """
    True = domain not registered / gone (confirm dead).
    False = domain still registered (keep even if DNS fails).
    None = inconclusive.
    """
    url = f"https://rdap.org/domain/{quote(domain.lower())}"
    try:
        request = Request(url, headers={**REQUEST_HEADERS, "Accept": "application/rdap+json"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        if exc.code == 404:
            return True
        return None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None

    statuses = {str(s).lower() for s in payload.get("status", [])}
    if statuses & {"redemption period", "pending delete", "client hold", "inactive"}:
        return True

    events = payload.get("events") or []
    now = time.time()
    for event in events:
        if not isinstance(event, dict):
            continue
        action = str(event.get("eventAction", "")).lower()
        if action != "expiration":
            continue
        date_str = event.get("eventDate")
        if not date_str:
            continue
        try:
            # RDAP dates are ISO-8601, often ending with Z
            normalized = str(date_str).replace("Z", "+00:00")
            from datetime import datetime

            expiry = datetime.fromisoformat(normalized).timestamp()
            if expiry < now:
                return True
        except (ValueError, TypeError, OSError):
            continue

    if payload.get("ldhName") or payload.get("handle"):
        return False

    return None


def probe_domain_liveness(domain: str) -> ProbeResult:
    """DNS consensus then WHOIS confirmation for NXDOMAIN hits."""
    dns_result = _dns_nxdomain_consensus(domain)
    if dns_result == "alive":
        return "alive"
    if dns_result == "inconclusive":
        return "inconclusive"

    whois = _rdap_domain_unregistered(domain)
    if whois is True:
        return "dead"
    if whois is False:
        return "alive"
    return "inconclusive"


def load_probe_cache() -> dict[str, tuple[int, ProbeStatus]]:
    """domain -> (unix_timestamp, status)."""
    cache: dict[str, tuple[int, ProbeStatus]] = {}

    if PROBE_CACHE_FILE.is_file():
        for raw in read_lines(PROBE_CACHE_FILE):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            domain = purify_hostname(parts[0])
            if not domain:
                continue
            checked_at = int(parts[1]) if parts[1].isdigit() else 0
            status_raw = parts[2] if len(parts) >= 3 else "alive"
            if status_raw not in ("alive", "dead", "dead_permanent"):
                status_raw = "alive"
            cache[domain] = (checked_at, status_raw)  # type: ignore[assignment]
        return cache

    # One-time migration from legacy verified + dead files.
    if VERIFIED_FILE.is_file():
        for raw in read_lines(VERIFIED_FILE):
            stripped = raw.strip()
            if not stripped:
                continue
            parts = stripped.split()
            domain = purify_hostname(parts[0]) if parts else None
            if not domain:
                continue
            checked_at = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
            cache[domain] = (checked_at, "alive")

    if DEAD_FILE.is_file():
        for domain in load_host_set(DEAD_FILE):
            if domain not in cache:
                cache[domain] = (0, "dead")

    return cache


def save_probe_cache(cache: dict[str, tuple[int, ProbeStatus]]) -> None:
    lines = [
        f"{domain} {checked_at} {status}"
        for domain, (checked_at, status) in sorted(cache.items())
    ]
    body = "\n".join(lines)
    PROBE_CACHE_FILE.write_text(body + ("\n" if body else ""), encoding="utf-8")


def _verified_ttl_seconds() -> int:
    days = int(os.environ.get("VERIFIED_TTL_DAYS", "30"))
    return max(1, days) * 86400


def _dead_recheck_ttl_seconds() -> int:
    days = int(os.environ.get("DEAD_RECHECK_DAYS", "90"))
    return max(1, days) * 86400


def _is_excluded_status(status: ProbeStatus) -> bool:
    return status in ("dead", "dead_permanent")


def _needs_probe(domain: str, cache: dict[str, tuple[int, ProbeStatus]], now: int) -> bool:
    entry = cache.get(domain)
    if entry is None:
        return True
    checked_at, status = entry
    if status == "dead_permanent":
        return False
    if status == "alive":
        return (now - checked_at) >= _verified_ttl_seconds()
    if status == "dead":
        if checked_at == 0:
            return True
        return (now - checked_at) >= _dead_recheck_ttl_seconds()
    return True


def prune_dead_domains(
    candidates: list[str],
    cache: dict[str, tuple[int, ProbeStatus]],
) -> tuple[list[str], dict[str, tuple[int, ProbeStatus]]]:
    """Probe via unfiltered public DoH + RDAP. Update probe_cache."""
    candidate_set = set(candidates)
    now = int(time.time())
    alive_ttl_days = _verified_ttl_seconds() // 86400
    dead_recheck_days = _dead_recheck_ttl_seconds() // 86400

    cache = {
        d: entry for d, entry in cache.items() if d in candidate_set or _is_excluded_status(entry[1])
    }

    excluded = {d for d, (_, status) in cache.items() if _is_excluded_status(status)}

    if os.environ.get("SKIP_DNS_CHECK", "").strip().lower() in ("1", "true", "yes"):
        print("SKIP_DNS_CHECK set — skipping public DNS probe")
        alive = [d for d in candidates if d not in excluded]
        return alive, cache

    resolvers = _dns_resolvers()
    resolver_names = ", ".join(name for name, _ in resolvers)
    print(f"DNS probe resolvers (unfiltered public DoH, not LAN): {resolver_names}")

    workers = max(1, int(os.environ.get("DNS_WORKERS", "64")))
    max_probe = max(0, int(os.environ.get("DNS_MAX_PROBE", "25000")))

    pending = sorted(d for d in candidate_set if _needs_probe(d, cache, now))
    fresh_count = sum(
        1
        for d in candidate_set
        if d in cache
        and cache[d][1] == "alive"
        and not _needs_probe(d, cache, now)
    )
    permanent_count = sum(1 for d in candidate_set if cache.get(d, (0, "alive"))[1] == "dead_permanent")

    if max_probe and len(pending) > max_probe:
        print(f"DNS probe budget: {max_probe} of {len(pending)} due for check this run")
        pending = pending[:max_probe]

    print(
        f"DNS probe: {len(pending)} domains "
        f"({fresh_count} fresh alive, {permanent_count} dead_permanent, "
        f"alive TTL {alive_ttl_days}d, dead re-check {dead_recheck_days}d)"
    )

    stats = {"alive": 0, "dead": 0, "dead_permanent": 0, "inconclusive": 0}

    if pending:

        def _probe_one(domain: str) -> tuple[str, ProbeResult]:
            return domain, probe_domain_liveness(domain)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_probe_one, d): d for d in pending}
            done = 0
            for future in as_completed(futures):
                domain = futures[future]
                done += 1
                if done % 500 == 0 or done == len(pending):
                    print(f"  DNS progress: {done}/{len(pending)}")

                prior_status: ProbeStatus | None = cache.get(domain, (0, "alive"))[1]

                try:
                    _, result = future.result()
                except Exception as exc:
                    print(f"  DNS error for {domain}: {exc}", file=sys.stderr)
                    cache[domain] = (now, "alive")
                    stats["inconclusive"] += 1
                    continue

                if result == "alive":
                    cache[domain] = (now, "alive")
                    stats["alive"] += 1
                elif result == "dead":
                    if prior_status == "dead":
                        cache[domain] = (now, "dead_permanent")
                        stats["dead_permanent"] += 1
                    else:
                        cache[domain] = (now, "dead")
                        stats["dead"] += 1
                else:
                    if prior_status == "alive":
                        cache[domain] = (now, "alive")
                    elif prior_status in ("dead", "dead_permanent"):
                        pass
                    else:
                        cache[domain] = (now, "alive")
                    stats["inconclusive"] += 1

    if any(stats[k] for k in stats):
        print(
            "Probe results: "
            f"{stats['alive']} alive, {stats['dead']} newly dead, "
            f"{stats['dead_permanent']} dead_permanent, "
            f"{stats['inconclusive']} inconclusive (kept)"
        )

    excluded = {d for d, (_, status) in cache.items() if _is_excluded_status(status)}
    alive = [d for d in candidates if d not in excluded]
    return alive, cache


def build_blocklist() -> tuple[list[str], dict[str, str], list[str]]:
    hosts: set[str] = set()
    sources: dict[str, str] = {}
    source_order: list[str] = []

    for url in load_url_sources():
        print(f"Fetching {url}")
        source_order.append(url)
        collect_hosts_with_source(fetch_list(url), url, hosts, sources)

    print(f"Loading local blacklist from {BLACKLIST_FILE}")
    source_order.append(BLACKLIST_SOURCE)
    collect_hosts_with_source(read_lines(BLACKLIST_FILE), BLACKLIST_SOURCE, hosts, sources)

    candidates = sorted(hosts)
    print(f"Merged {len(candidates)} unique domains (sorted)")

    cache = load_probe_cache()
    alive, cache = prune_dead_domains(candidates, cache)
    save_probe_cache(cache)

    dead_export = {
        d for d, (_, status) in cache.items() if status in ("dead", "dead_permanent")
    }
    save_host_set(DEAD_FILE, dead_export)

    whitelist = load_whitelist()
    print(f"Whitelist entries: {len(whitelist)}")

    excluded = {d for d, (_, status) in cache.items() if _is_excluded_status(status)}
    after_whitelist = [d for d in alive if d not in whitelist]
    final = sorted(d for d in after_whitelist if d not in excluded)
    final_sources = {d: sources.get(d, BLACKLIST_SOURCE) for d in final}

    print(
        f"Final list: {len(final)} domains "
        f"({len(dead_export)} in dead/dead_permanent, removed from output)"
    )
    return final, final_sources, source_order


def format_dnscrypt_blocklist(
    domains: list[str],
    domain_sources: dict[str, str],
    source_order: list[str],
) -> str:
    """DNSCrypt blocked_names file with section-per-source headers."""
    by_source: dict[str, list[str]] = {}
    for domain in domains:
        source = domain_sources.get(domain, BLACKLIST_SOURCE)
        by_source.setdefault(source, []).append(domain)

    ordered_sources = [s for s in source_order if s in by_source]
    for source in sorted(by_source):
        if source not in ordered_sources:
            ordered_sources.append(source)

    lines = [
        "###########################",
        "#        Blocklist        ",
        "###########################",
        "# ADios — https://github.com/AlexRabbit/ADios",
        "# Generated by config/build_hosts.py",
        "# Plain domain = blocks domain + subdomains (DNSCrypt blocked_names)",
        "",
    ]

    for source in ordered_sources:
        section_domains = sorted(by_source[source], key=_name_cmp)
        if not section_domains:
            continue
        lines.append(f"########## Blocklist from {source} ##########")
        lines.append("")
        lines.extend(section_domains)
        lines.append("")

    body = "\n".join(lines).rstrip()
    return body + "\n"


def write_outputs(
    domains: list[str],
    domain_sources: dict[str, str],
    source_order: list[str],
) -> None:
    OUTPUT_PIHOLE.write_text("\n".join(domains) + ("\n" if domains else ""), encoding="utf-8")

    hosts_lines = [f"0.0.0.0 {d}" for d in domains]
    hosts_body = "\n".join(hosts_lines) + ("\n" if hosts_lines else "")
    OUTPUT_HOSTS.write_text(hosts_body, encoding="utf-8")

    OUTPUT_DNSCRYPT.write_text(
        format_dnscrypt_blocklist(domains, domain_sources, source_order),
        encoding="utf-8",
    )

    adguard_lines = [f"||{d}^" for d in domains]
    adguard_body = "\n".join(adguard_lines) + ("\n" if adguard_lines else "")
    OUTPUT_ADGUARD.write_text(adguard_body, encoding="utf-8")


def main() -> None:
    ensure_runtime()

    if not DEAD_FILE.is_file():
        DEAD_FILE.write_text("", encoding="utf-8")

    for path, label in (
        (LISTS_FILE, "lists"),
        (BLACKLIST_FILE, "blacklist"),
        (WHITELIST_FILE, "whitelist"),
    ):
        if not path.is_file():
            print(f"Error: missing config file {label} ({path})", file=sys.stderr)
            sys.exit(1)

    domains, domain_sources, source_order = build_blocklist()
    write_outputs(domains, domain_sources, source_order)

    print(
        f"Wrote {len(domains)} domains -> "
        f"{OUTPUT_PIHOLE.name}, {OUTPUT_HOSTS.name}, "
        f"{OUTPUT_DNSCRYPT.name}, {OUTPUT_ADGUARD.name}"
    )


if __name__ == "__main__":
    main()
