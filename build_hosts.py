#!/usr/bin/env python3
"""
Build unified hosts file from blacklist URLs, local sources, then apply whitelist.
Outputs host.txt (plain domains) and 0host.txt / hosts (0.0.0.0 format).
"""

import requests

# Read online sources (URLs) from the blacklist.txt file
blacklist_sources = []
with open("blacklist.txt", "r") as blacklist_file:
    blacklist_sources = [u.strip() for u in blacklist_file.read().splitlines() if u.strip()]

# List of local .txt files with host entries
local_sources = [
    "block2.txt",
]

# List of hosts to whitelist
whitelist_sources = [
    "whitelist.txt",
]

all_hosts_set = set()

# Fetch host entries from online sources
for source_url in blacklist_sources:
    if source_url.startswith("#"):
        continue
    try:
        response = requests.get(source_url, timeout=30)
        if response.status_code == 200:
            host_entries = response.text.splitlines()
            all_hosts_set.update(host_entries)
        else:
            print(f"Failed to fetch hosts from {source_url}")
    except Exception as e:
        print(f"Error fetching hosts from {source_url}: {e}")

# Read host entries from local .txt files
for local_file in local_sources:
    try:
        with open(local_file, "r") as file:
            local_entries = file.read().splitlines()
            all_hosts_set.update(local_entries)
    except FileNotFoundError:
        print(f"Local file not found: {local_file} (skipping)")
    except Exception as e:
        print(f"Error reading local file {local_file}: {e}")

# Normalize: lowercase, remove prefixes, strip
def normalize(entry):
    s = entry.lower().strip()
    s = s.replace("0.0.0.0 ", "").replace("127.0.0.1 ", "").replace("127.0.0.1\t", "")
    s = s.replace("*.", "").replace("https://www.", "").replace("http://www.", "")
    s = s.replace("https://", "").replace("http://", "").replace("www.", "")
    for x in ("  ", " ", "\t", "||", "^", "|"):
        s = s.replace(x, "")
    # Keep only the host part (first segment if path-like)
    if "/" in s and not s.startswith("#"):
        s = s.split("/")[0]
    return s

all_hosts_cleaned = set()
for host_entry in all_hosts_set:
    cleaned = normalize(host_entry)
    if cleaned and not cleaned.startswith("#"):
        all_hosts_cleaned.add(cleaned)

all_hosts_cleaned = sorted(all_hosts_cleaned)
all_hosts_cleaned = [line for line in all_hosts_cleaned if not line.startswith(("#", "!"))]

# Load whitelist
whitelist_set = set()
for whitelist_file in whitelist_sources:
    try:
        with open(whitelist_file, "r") as file:
            for line in file:
                w = normalize(line)
                if w and not w.startswith("#"):
                    whitelist_set.add(w)
    except FileNotFoundError:
        print(f"Whitelist file not found: {whitelist_file} (skipping)")
    except Exception as e:
        print(f"Error reading whitelist file {whitelist_file}: {e}")

# Remove whitelisted
final_hosts = [h for h in all_hosts_cleaned if h not in whitelist_set]

# Write host.txt (plain domains)
with open("host.txt", "w") as f:
    f.write("\n".join(final_hosts))

# Write 0host.txt and hosts (0.0.0.0 format)
lines_0 = ["0.0.0.0 " + h for h in final_hosts]
with open("0host.txt", "w") as f:
    f.write("\n".join(lines_0) + "\n")
with open("hosts", "w") as f:
    f.write("\n".join(lines_0) + "\n")

# Copy to PIHOLE/hosts if directory exists
import os
if os.path.isdir("PIHOLE"):
    with open("PIHOLE/hosts", "w") as f:
        f.write("\n".join(lines_0) + "\n")

print("Hosts built: host.txt, 0host.txt, hosts" + (" (and PIHOLE/hosts)" if os.path.isdir("PIHOLE") else ""))
