#!/usr/bin/env python3
"""
ADios blocklist builder.

Reads lists, blacklist, whitelist, and dead from this directory (config/).
Writes pihole-hosts, hosts, and dnscrypt-hosts at the repository root.

Pipeline: merge sources → dedupe/sort → DNS probe (verified TTL + dead) → whitelist
→ dead filter → write outputs.

DNS probe uses Google + Cloudflare DoH (not your LAN). Optional env:
  SKIP_DNS_CHECK=1      skip probing (fast local build)
  DNS_WORKERS=64        parallel probes
  DNS_MAX_PROBE=25000   max domains checked per run
  VERIFIED_TTL_DAYS=30  re-check verified domains after this many days (~monthly)

Runtime: Python 3.9+ only — standard library, no pip, no requirements.txt.
On a clean VPS/PC: clone the repo, then:
  python3 config/build_hosts.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
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
VERIFIED_FILE = CONFIG / "verified"

# Public DNS-over-HTTPS (no local resolver; works on GitHub Actions / clean VPS).
DNS_ENDPOINTS = (
    "https://dns.google/resolve?name={name}&type={rtype}",
    "https://1.1.1.1/dns-query?name={name}&type={rtype}",
)

OUTPUT_PIHOLE = ROOT / "pihole-hosts"
OUTPUT_HOSTS = ROOT / "hosts"
OUTPUT_DNSCRYPT = ROOT / "dnscrypt-hosts"

REQUEST_HEADERS = {
    "User-Agent": "ADios-build-hosts/1.0 (+https://github.com/AlexRabbit/ADios)",
}

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
        parsed = urlparse(line)
        line = (parsed.hostname or "").lower()
    elif line.startswith("//"):
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


def collect_hosts(lines: list[str], bucket: set[str]) -> None:
    for raw in lines:
        for host in hosts_from_line(raw):
            bucket.add(host)


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


def load_verified() -> dict[str, int]:
    """domain -> unix time of last successful DNS check."""
    verified: dict[str, int] = {}
    for raw in read_lines(VERIFIED_FILE):
        stripped = raw.strip()
        if not stripped:
            continue
        parts = stripped.split()
        domain = purify_hostname(parts[0]) if parts else None
        if not domain:
            domain = purify_hostname(stripped)
        if not domain:
            continue
        checked_at = 0
        if len(parts) >= 2 and parts[1].isdigit():
            checked_at = int(parts[1])
        verified[domain] = checked_at
    return verified


def save_verified(verified: dict[str, int]) -> None:
    lines = [f"{domain} {checked_at}" for domain, checked_at in sorted(verified.items())]
    body = "\n".join(lines)
    VERIFIED_FILE.write_text(body + ("\n" if body else ""), encoding="utf-8")


def _verified_ttl_seconds() -> int:
    days = int(os.environ.get("VERIFIED_TTL_DAYS", "30"))
    return max(1, days) * 86400


def _is_verified_fresh(domain: str, verified: dict[str, int], now: int) -> bool:
    checked_at = verified.get(domain)
    if checked_at is None:
        return False
    return (now - checked_at) < _verified_ttl_seconds()


def _dns_query(domain: str, rtype: str) -> tuple[int | None, bool]:
    """Query public DoH. Returns (status_code, has_answer). status None = transport error."""
    headers = {**REQUEST_HEADERS, "Accept": "application/dns-json"}
    for template in DNS_ENDPOINTS:
        url = template.format(name=quote(domain), rtype=rtype)
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            status = int(payload.get("Status", 2))
            answers = payload.get("Answer") or []
            return status, bool(answers)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
            continue
    return None, False


def domain_is_alive(domain: str) -> bool:
    """
    True = keep domain (resolves or check was inconclusive).
    False = NXDOMAIN on all public resolvers (expired / dead name).
    """
    statuses: list[int | None] = []
    any_answer = False

    for rtype in ("A", "AAAA"):
        status, has_answer = _dns_query(domain, rtype)
        statuses.append(status)
        if has_answer:
            any_answer = True

    if any_answer:
        return True

    nxdomain = [s for s in statuses if s is not None]
    if nxdomain and all(s == 3 for s in nxdomain):
        return False

    return True


def prune_dead_domains(
    candidates: list[str],
    dead: set[str],
    verified: dict[str, int],
) -> tuple[list[str], set[str], dict[str, int]]:
    """
    Probe via public DNS. Verified entries expire after VERIFIED_TTL_DAYS and are
    re-checked; failures move to dead and are removed from verified.
    """
    candidate_set = set(candidates)
    now = int(time.time())
    ttl_days = _verified_ttl_seconds() // 86400

    verified = {d: ts for d, ts in verified.items() if d in candidate_set and d not in dead}

    if os.environ.get("SKIP_DNS_CHECK", "").strip().lower() in ("1", "true", "yes"):
        print("SKIP_DNS_CHECK set — skipping public DNS probe")
        return [d for d in candidates if d not in dead], dead, verified

    workers = max(1, int(os.environ.get("DNS_WORKERS", "64")))
    max_probe = max(0, int(os.environ.get("DNS_MAX_PROBE", "25000")))

    stale = sorted(
        (d for d in candidate_set if d not in dead and d in verified and not _is_verified_fresh(d, verified, now)),
        key=lambda d: verified.get(d, 0),
    )
    unchecked = sorted(d for d in candidate_set if d not in dead and d not in verified)
    pending = stale + unchecked

    fresh_count = sum(1 for d in candidate_set if d not in dead and _is_verified_fresh(d, verified, now))

    if max_probe and len(pending) > max_probe:
        print(f"DNS probe budget: {max_probe} of {len(pending)} due for check this run")
        pending = pending[:max_probe]

    print(
        f"DNS probe: {len(pending)} domains via public DoH "
        f"({fresh_count} fresh verified, {len(stale)} stale, {len(unchecked)} new, "
        f"{len(dead)} dead, TTL {ttl_days}d)"
    )

    newly_dead: set[str] = set()
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(domain_is_alive, d): d for d in pending}
            done = 0
            for future in as_completed(futures):
                domain = futures[future]
                done += 1
                if done % 2000 == 0 or done == len(pending):
                    print(f"  DNS progress: {done}/{len(pending)}")
                try:
                    if future.result():
                        verified[domain] = now
                    else:
                        newly_dead.add(domain)
                        verified.pop(domain, None)
                except Exception as exc:
                    print(f"  DNS error for {domain}: {exc}", file=sys.stderr)
                    verified[domain] = now

    if newly_dead:
        dead |= newly_dead
        print(f"Marked {len(newly_dead)} dead domains (config/dead); removed from verified")

    verified = {d: ts for d, ts in verified.items() if d not in dead}

    alive = [d for d in candidates if d not in dead]
    return alive, dead, verified


def build_blocklist() -> list[str]:
    hosts: set[str] = set()

    for url in load_url_sources():
        print(f"Fetching {url}")
        collect_hosts(fetch_list(url), hosts)

    print(f"Loading local blacklist from {BLACKLIST_FILE}")
    collect_hosts(read_lines(BLACKLIST_FILE), hosts)

    candidates = sorted(hosts)
    print(f"Merged {len(candidates)} unique domains (sorted)")

    dead = load_host_set(DEAD_FILE)
    verified = load_verified() if VERIFIED_FILE.is_file() else {}
    verified = {d: ts for d, ts in verified.items() if d not in dead}

    alive, dead, verified = prune_dead_domains(candidates, dead, verified)
    save_host_set(DEAD_FILE, dead)
    save_verified(verified)

    whitelist = load_whitelist()
    print(f"Whitelist entries: {len(whitelist)}")

    after_whitelist = [d for d in alive if d not in whitelist]
    final = sorted(d for d in after_whitelist if d not in dead)
    print(f"Final list: {len(final)} domains ({len(dead)} in dead, removed from output)")
    return final


def write_outputs(domains: list[str]) -> None:
    OUTPUT_PIHOLE.write_text("\n".join(domains) + ("\n" if domains else ""), encoding="utf-8")

    hosts_lines = [f"0.0.0.0 {d}" for d in domains]
    hosts_body = "\n".join(hosts_lines) + ("\n" if hosts_lines else "")
    OUTPUT_HOSTS.write_text(hosts_body, encoding="utf-8")

    OUTPUT_DNSCRYPT.write_text(
        "\n".join(domains) + ("\n" if domains else ""),
        encoding="utf-8",
    )


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

    domains = build_blocklist()
    write_outputs(domains)

    print(
        f"Wrote {len(domains)} domains -> "
        f"{OUTPUT_PIHOLE.name}, {OUTPUT_HOSTS.name}, {OUTPUT_DNSCRYPT.name}"
    )


if __name__ == "__main__":
    main()
