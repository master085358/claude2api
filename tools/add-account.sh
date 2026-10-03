#!/usr/bin/env bash
# Add/update account from cURL clipboard (DevTools > Copy as cURL).
# Usage: ./tools/add-account.sh

CONFIG_FILE="/home/art/code/claude2api/config.yaml"
PROXIES_FILE="/home/art/.my-sys-env/proxies.txt"

echo "=== Add/Update Account (cURL) ==="

if [ ! -f "$CONFIG_FILE" ]; then echo "ERROR: config not found" >&2; exit 1; fi
if [ ! -f "$PROXIES_FILE" ]; then echo "ERROR: proxies not found" >&2; exit 1; fi

if [ -z "${DISPLAY:-}" ]; then export DISPLAY=":0"; fi
CLIPBOARD="$(xclip -selection clipboard -o 2>/dev/null)" || true
if [ -z "$CLIPBOARD" ]; then
    echo "ERROR: clipboard empty. Copy as cURL from DevTools first." >&2; exit 1
fi
echo "[1] Clipboard: ${#CLIPBOARD} chars"

ORG_ID=$(echo "$CLIPBOARD" | grep -oP '/organizations/\K[a-f0-9-]+(?=/)' | head -1)
if [ -z "$ORG_ID" ]; then
    echo "ERROR: no orgID found" >&2; exit 1
fi
echo "[2] OrgID: $ORG_ID"

EXISTING_NAME=$(grep -A5 "orgID: \"$ORG_ID\"" "$CONFIG_FILE" 2>/dev/null | grep -oP 'name:\s*"\K[^"]*' || true)
if [ -n "$EXISTING_NAME" ]; then
    echo "[3] Exists: \"$EXISTING_NAME\" -> UPDATING"
    ACCOUNT_NAME="$EXISTING_NAME"
else
    echo "[3] New account. Enter name:"
    read -r ACCOUNT_NAME
    if [ -z "$ACCOUNT_NAME" ]; then echo "ERROR: name empty" >&2; exit 1; fi
fi

TMPFILE=$(mktemp /tmp/claude2api_XXXXXX.txt)
printf '%s' "$CLIPBOARD" > "$TMPFILE"
python3 /home/art/code/claude2api/tools/add_account.py "$TMPFILE" "$PROXIES_FILE" "$CONFIG_FILE" "$ACCOUNT_NAME"
RESULT=$?
rm -f "$TMPFILE"

if [ $RESULT -ne 0 ]; then echo "ERROR: failed" >&2; exit 1; fi
echo ""
echo "[4] Done. Restart: pkill -f './claude2api'; cd /home/art/code/claude2api && ./claude2api"
