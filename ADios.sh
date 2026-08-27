#!/usr/bin/env bash
# ADios blocklist builder launcher — AlexRabbit
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "  ============================================"
echo "   ADios - Say Goodbye to Ads"
echo "   by AlexRabbit"
echo "  ============================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "  [ERROR] python3 3.9+ is required."
  exit 1
fi

python3 config/build_hosts.py

echo ""
echo "  [OK] Build complete."
echo "  Outputs: hosts, pihole-hosts, dnscrypt-hosts, adguardhosts.txt, remover.txt"
echo ""
