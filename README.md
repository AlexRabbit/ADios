# ADios

Blocklists for DNS and browser adblockers. Maintained by [AlexRabbit](https://github.com/AlexRabbit).

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Auto-update](https://img.shields.io/badge/Auto--update-48h-green.svg)](.github/workflows/update-hosts.yml)

---

[![Subscribe to ADiosBlocker](https://img.shields.io/badge/Subscribe-ADiosBlocker-2ea44f?style=for-the-badge&logo=adguard&logoColor=white)](https://raw.githubusercontent.com/AlexRabbit/ADios/master/ADiosBlocker)

**Browser only** — AdGuard extension, uBlock Origin. Paste that URL under custom / imported filter lists.

**Not for AdGuard Home.** Home is DNS-only; use the table below instead.

---

## DNS blocklists (download)

Same domains, different formats. Pick the row that matches your tool.

| Use with | File | Raw URL |
|----------|------|---------|
| Windows / macOS / Linux `hosts` file | [hosts](hosts) | https://raw.githubusercontent.com/AlexRabbit/ADios/master/hosts |
| Pi-hole | [pihole-hosts](pihole-hosts) | https://raw.githubusercontent.com/AlexRabbit/ADios/master/pihole-hosts |
| AdGuard Home | [adguardhosts.txt](adguardhosts.txt) | https://raw.githubusercontent.com/AlexRabbit/ADios/master/adguardhosts.txt |
| DNSCrypt-proxy | [dnscrypt-hosts](dnscrypt-hosts) | https://raw.githubusercontent.com/AlexRabbit/ADios/master/dnscrypt-hosts |

Lists rebuild every 48 hours via GitHub Actions.

---

## DNS lists vs ADiosBlocker

| | DNS lists (`hosts`, `pihole-hosts`, etc.) | [ADiosBlocker](ADiosBlocker) |
|---|-------------------------------------------|------------------------------|
| **Blocks at** | DNS / network level | Browser only |
| **Works in** | Pi-hole, AdGuard Home, system hosts, DNSCrypt | AdGuard extension, uBlock Origin |
| **Content** | Domain names only | Full filter rules (`\|\|domain^`, cosmetics, `$redirect`, scriptlets) |
| **Built from** | [`config/lists`](config/lists) | [`config/lists2`](config/lists2) |
| **Builder** | [`config/build_hosts.py`](config/build_hosts.py) | [`config/build_adblock.py`](config/build_adblock.py) |

Do not import **ADiosBlocker** into AdGuard Home or Pi-hole — those tools cannot run cosmetic or script rules and will ignore or choke on most of the file.

Do not merge **lists2** into **lists** — filter rules are not hostnames.

---

## Quick install

**Windows hosts file**

1. Download [hosts](https://raw.githubusercontent.com/AlexRabbit/ADios/master/hosts)
2. Back up `C:\Windows\System32\drivers\etc\hosts`
3. Append the downloaded entries (or replace — your call)
4. `ipconfig /flushdns`

**Pi-hole / AdGuard Home**

Add the raw URL from the table above as a blocklist subscription.

**Browser**

Use the green **Subscribe** button at the top.

---

## Build locally

Python 3.9+, no pip.

```bash
python3 config/build_hosts.py    # DNS lists
python3 config/build_adblock.py  # ADiosBlocker
```

| File | Purpose |
|------|---------|
| [`config/lists`](config/lists) | Hosts / domain source URLs |
| [`config/lists2`](config/lists2) | Browser filter source URLs |
| [`config/blacklist`](config/blacklist) | Extra domains to block |
| [`config/whitelist`](config/whitelist) | Domains to never block |
| [`config/remover`](config/remover) | Domains to drop (dead / manual) |

Fast rebuild without DNS probing: `SKIP_DNS_CHECK=1 python3 config/build_hosts.py`

---

## FAQ

**Do I need to build if I use the raw URLs?**  
No. The repo files are kept up to date automatically.

**Spotify / Twitch broken?**  
Something may need whitelisting — open an issue with the domain.

**Why is `config/remover` huge?**  
Dead and expired domains pulled out of upstream lists so the DNS outputs stay lean.

---

## License

GPL-3.0 — [AlexRabbit](https://github.com/AlexRabbit).  
Upstream list authors keep their own licenses; sources are listed in [`config/lists`](config/lists) and [`config/lists2`](config/lists2).
