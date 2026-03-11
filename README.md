# ADios

**A unified, auto-updated hosts-based blocklist.** One list, many formats—for your system hosts file, Pi-hole, AdGuard, DNSMasq, and more.

---

## What This Is

ADios is a **merged and deduplicated blocklist** delivered in standard **hosts format** (`0.0.0.0 domain.com`). It combines:

- **Upstream lists** from trusted projects (AdAway, Steven Black, AdGuard, OISD, URLhaus, and others)
- **Curated additions** for streaming and app ads (e.g. Twitch, Spotify)
- **Whitelisting** so essential domains (e.g. for Spotify or Twitch to work) stay unblocked

The list is **rebuilt automatically every day** on GitHub Actions. You get a single, clean `hosts` file (and a Pi-hole–friendly copy) without running anything yourself.

---

## How Hosts Blocking Works

- Your OS uses a **hosts file** to map hostnames to IP addresses. It is checked **before** DNS ([RFC 6761](https://www.rfc-editor.org/rfc/rfc6761), and OS behavior is documented in [Microsoft](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2003/cc758994(v=ws.10)) and [Linux](https://man7.org/linux/man-pages/man5/hosts.5.html) docs).
- Sending a hostname to **`0.0.0.0`** (or `127.0.0.1`) makes the OS resolve it locally, so the connection never reaches the real server. That’s the standard way to block domains via hosts.
- The same format is used by Pi-hole, AdGuard Home, and many DNS-level blockers, so one list can serve multiple use cases.

---

## What Gets Blocked

| Category | Description |
|----------|-------------|
| **Ads & trackers** | Common ad and analytics domains from the included lists |
| **Streaming ads** | Twitch, YouTube (Samsung TV list), and similar ad domains |
| **In-app ads** | Spotify, Deezer, and other in-app ad endpoints where possible |
| **Malware & abuse** | Domains from URLhaus and similar abuse lists |
| **Scam / spam** | Scam and spam domains from the included sources |
| **Optional adult ads** | Optional blocklist for adult ad networks (not adult content itself) |

Whitelisted domains (e.g. core Spotify/Twitch domains needed for playback) are **removed** from the final list so services keep working.

---

## Downloads

| File | Use case |
|------|----------|
| **[hosts](https://raw.githubusercontent.com/AlexRabbit/ADios/master/hosts)** | System hosts file, AdGuard, DNSMasq, etc. |
| **[PIHOLE/hosts](https://raw.githubusercontent.com/AlexRabbit/ADios/master/PIHOLE/hosts)** | Pi-hole blocklist (same content, `0.0.0.0` format) |

**System hosts (Windows):**  
`C:\Windows\System32\drivers\etc\hosts`  
**System hosts (macOS/Linux):**  
`/etc/hosts`

Copy the raw content of `hosts` into your hosts file (back up the original first). Clear browser cache after changing hosts.

---

## Compatibility

- **Windows, macOS, Linux** — use the `hosts` file as above.
- **Pi-hole** — use the list URL or the raw `PIHOLE/hosts` file.
- **AdGuard / AdGuard Home** — supports hosts-style blocklists.
- **DNSMasq** — use `addn-hosts` or the same format.
- **Response Policy Zone (RPZ)** — can be built from the same domain list.

---

## Build It Yourself

The list is produced by a Python script that:

1. Fetches all URLs in `blacklist.txt`
2. Merges local lists (e.g. `block2.txt`)
3. Normalizes and deduplicates entries
4. Applies `whitelist.txt`
5. Writes `hosts` and `PIHOLE/hosts` in `0.0.0.0` format

**Requirements:** Python 3.8+, `requests`.

```bash
pip install -r requirements.txt
python build_hosts.py
```

Outputs: `host.txt` (domains only), `0host.txt`, `hosts`, and `PIHOLE/hosts` (if the `PIHOLE` directory exists).

---

## Auto-Update (GitHub Actions)

The repository uses **GitHub Actions** to rebuild the list **daily** on GitHub’s runners:

- **Schedule:** once per day (cron)
- **Manual run:** **Actions** → **Update hosts** → **Run workflow**

Only the built `hosts` (and `PIHOLE/hosts`) are committed; the workflow does not re-run on its own commit (`[skip ci]`).

---

## Backup Hosts File

Before replacing your hosts file, keep a clean copy. For a default Windows hosts file, see:  
[winhelp2002.mvps.org](http://winhelp2002.mvps.org/defaultwin7-hosts.zip).

---

## Sources (Upstream Lists)

The list aggregates from public, community-maintained blocklists, including (among others):

- AdAway, Steven Black’s unified hosts, AdGuard filters
- OISD, FadeMind, Soteria-Nou, URLhaus (abuse.ch)
- Pgl.yoyo.org, Someone Who Cares, MVPS
- Specialized lists for YouTube, Samsung TV, Twitch, Spotify

See `blacklist.txt` in the repo for the full URL list. We do not control those projects; we only merge and deduplicate their output and add our own whitelist.

---

## License

[GPL-3.0](LICENSE). Same for the build script and config; upstream lists keep their respective licenses.

---

**ADios** — one list, auto-updated, for hosts-based blocking everywhere.
