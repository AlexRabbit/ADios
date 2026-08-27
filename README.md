If this helped you, consider starring the repo ⭐

# ADios ADS
## Ultimate ADblocker for both: Hostlists and Addons AWAYS UPDATED
### Use the correct for your addon or hostlists (They arent the same) You can also duel use them at the same time!

Blocklists for DNS and browser adblockers. Maintained by [AlexRabbit](https://github.com/AlexRabbit).

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Auto-update](https://img.shields.io/badge/Auto--update-48h-green.svg)](.github/workflows/update-hosts.yml)

---



**Browser only** — AdGuard extension, uBlock Origin. Paste that URL under custom / imported filter lists.
[![Subscribe to ADiosBlocker](https://img.shields.io/badge/Subscribe-ADiosBlocker-2ea44f?style=for-the-badge&logo=adguard&logoColor=white)](https://raw.githubusercontent.com/AlexRabbit/ADios/master/ADiosBlocker)
Just click the Green Button to import it to your Adblock Addon!

---

## ADhost Lists - DNS blocklists

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
