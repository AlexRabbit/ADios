#!/usr/bin/env python3
"""
ADiosBlocker — browser adblock filter list builder.

Reads filter-list URLs from config/lists2 (NOT hosts lists).
Writes ADiosBlocker at the repository root for AdGuard / uBlock Origin.

Pipeline: fetch sources → parse filter rules → deduplicate → write merged list.

Runtime: Python 3.9+ only — standard library, no pip.
  python3 config/build_adblock.py

Optional env:
  ADBLOCK_WORKERS=16   parallel URL fetch threads
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MIN_PYTHON = (3, 9)

CONFIG = Path(__file__).resolve().parent
ROOT = CONFIG.parent
LISTS2_FILE = CONFIG / "lists2"
OUTPUT = ROOT / "ADiosBlocker"

REQUEST_HEADERS = {
    "User-Agent": "ADios-build-adblock/1.0 (+https://github.com/AlexRabbit/ADios)",
}

_UPSTREAM_META_PREFIXES = (
    "! title:",
    "! homepage:",
    "! expires:",
    "! description:",
    "! license:",
    "! version:",
    "! last modified:",
    "! last updated:",
    "! redirect:",
    "! homepage url:",
    "! checksum:",
    "! diffurl:",
    "! author:",
)


def ensure_runtime() -> None:
    if sys.version_info < MIN_PYTHON:
        need = ".".join(str(n) for n in MIN_PYTHON)
        print(f"Error: Python {need}+ required (found {sys.version.split()[0]})", file=sys.stderr)
        sys.exit(1)


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        print(f"Error: missing file {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def load_url_sources() -> list[str]:
    lines = read_lines(LISTS2_FILE)
    return [u.strip() for u in lines if u.strip() and not u.strip().startswith("#")]


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


def _is_upstream_metadata(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("!"):
        return False
    lower = stripped.lower()
    return any(lower.startswith(prefix) for prefix in _UPSTREAM_META_PREFIXES)


def normalize_rule(line: str) -> str | None:
    """Return dedup key for a rule line, or None if skippable."""
    s = line.strip()
    if not s:
        return None
    if s.startswith("!"):
        return None
    if s.lower().startswith("[adblock"):
        return None
    if s.startswith("||") or s.startswith("@@||"):
        return s.lower()
    return s


def extract_rules(lines: list[str]) -> list[str]:
    """Pull filter rules from raw list lines, preserving original text."""
    rules: list[str] = []
    for raw in lines:
        if _is_upstream_metadata(raw):
            continue
        key = normalize_rule(raw)
        if key is not None:
            rules.append(raw.strip())
    return rules


def build_header() -> list[str]:
    return [
        "! Title: ADiosBlocker",
        "! Description: Merged browser adblock rules by AlexRabbit",
        "! Homepage: https://github.com/AlexRabbit/ADios",
        "! Author: AlexRabbit",
        "! License: https://github.com/AlexRabbit/ADios/blob/master/LICENSE",
        "! Expires: 2 days",
        "",
        "[Adblock Plus 2.0]",
        "",
    ]


def merge_filter_lists() -> tuple[list[str], dict[str, int]]:
    urls = load_url_sources()
    if not urls:
        print("Error: no URLs in config/lists2", file=sys.stderr)
        sys.exit(1)

    workers = max(1, int(os.environ.get("ADBLOCK_WORKERS", "16")))
    fetched: dict[str, list[str]] = {}

    print(f"Fetching {len(urls)} filter lists ({workers} workers)")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_list, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                fetched[url] = future.result()
            except Exception as exc:
                print(f"Error fetching {url}: {exc}", file=sys.stderr)
                fetched[url] = []

    seen: set[str] = set()
    output_lines = build_header()
    stats: dict[str, int] = {
        "sources": len(urls),
        "rules_written": 0,
        "duplicates_skipped": 0,
        "sources_empty": 0,
    }

    for url in urls:
        lines = fetched.get(url, [])
        rules = extract_rules(lines)
        if not rules:
            stats["sources_empty"] += 1
            print(f"  Warning: no rules from {url}", file=sys.stderr)
            continue

        section_added = 0
        section_dupes = 0
        section_lines: list[str] = []

        for rule in rules:
            key = normalize_rule(rule)
            if key is None:
                continue
            if key in seen:
                section_dupes += 1
                continue
            seen.add(key)
            section_lines.append(rule)
            section_added += 1

        if not section_lines:
            continue

        output_lines.append(f"! ----- {url} -----")
        output_lines.extend(section_lines)
        output_lines.append("")

        stats["rules_written"] += section_added
        stats["duplicates_skipped"] += section_dupes
        print(
            f"  {url}: {len(rules)} fetched, "
            f"{section_added} unique, {section_dupes} duplicates skipped"
        )

    return output_lines, stats


def write_output(lines: list[str]) -> None:
    body = "\n".join(lines).rstrip()
    OUTPUT.write_text(body + "\n", encoding="utf-8")


def main() -> None:
    ensure_runtime()

    lines, stats = merge_filter_lists()
    if stats["rules_written"] == 0:
        print("Error: no rules written — check config/lists2 URLs", file=sys.stderr)
        sys.exit(1)

    write_output(lines)
    print(
        f"Wrote {stats['rules_written']} unique rules -> {OUTPUT.name} "
        f"({stats['duplicates_skipped']} duplicates removed, "
        f"{stats['sources']} sources, {stats['sources_empty']} empty)"
    )


if __name__ == "__main__":
    main()
