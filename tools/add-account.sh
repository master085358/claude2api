#!/usr/bin/env bash
# Idempotent add/update account from clipboard fetch() request.
# Usage:
#   1. Copy fetch() from DevTools (Network > right-click > Copy as fetch)
#   2. Run: ./tools/add-account.sh [session_key]
#   If session_key not provided, will prompt for it.
#   If orgID is new, will prompt for account name.
#   If orgID exists, name is kept from config.

CONFIG_FILE="/home/art/code/claude2api/config.yaml"
PROXIES_FILE="/home/art/.my-sys-env/proxies.txt"
SCRIPT_DIR="/home/art/code/claude2api/tools"

echo "=== Add/Update Account (idempotent) ==="
echo ""

# Step 1: Check files
echo "[1/6] Checking files..."
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: $CONFIG_FILE not found" >&2
    exit 1
fi
if [ ! -f "$PROXIES_FILE" ]; then
    echo "ERROR: $PROXIES_FILE not found" >&2
    exit 1
fi
echo "  OK"

# Step 2: Read clipboard
echo "[2/6] Reading clipboard..."
if [ -z "${DISPLAY:-}" ]; then
    export DISPLAY=":0"
fi

CLIPBOARD="$(xclip -selection clipboard -o 2>/dev/null)" || true
if [ -z "$CLIPBOARD" ]; then
    echo "ERROR: clipboard is empty or xclip failed." >&2
    echo "  Copy a fetch() request from DevTools first." >&2
    exit 1
fi
echo "  OK: ${#CLIPBOARD} chars"

# Step 3: Get session key
echo "[3/6] Session key..."
if [ -n "${1:-}" ]; then
    SESSION_KEY="$1"
    echo "  From argument: ${SESSION_KEY:0:40}..."
else
    echo "  Paste sessionKey (from DevTools > Application > Cookies > sessionKey):"
    read -r SESSION_KEY
    if [ -z "$SESSION_KEY" ]; then
        echo "ERROR: session key is empty" >&2
        exit 1
    fi
    echo "  OK: ${SESSION_KEY:0:40}..."
fi

# Step 4: Extract orgID to check if account exists
echo "[4/6] Checking if account exists..."
TMPFILE=$(mktemp /tmp/claude2api_clip_XXXXXX.txt)
printf '%s' "$CLIPBOARD" > "$TMPFILE"

ORG_ID=$(python3 -c "
import re, sys
with open('$TMPFILE') as f:
    text = f.read()
urls = re.findall(r'fetch\(\"([^\"]+)\"', text)
for u in urls:
    if '/completion' in u and 'chat_conversations' in u:
        m = re.search(r'/organizations/([a-f0-9-]+)/', u)
        if m:
            print(m.group(1))
            sys.exit(0)
sys.exit(1)
" 2>/dev/null)

if [ -z "$ORG_ID" ]; then
    echo "ERROR: could not extract orgID from clipboard" >&2
    rm -f "$TMPFILE"
    exit 1
fi
echo "  OrgID: $ORG_ID"

# Check if this orgID already has a name in config
EXISTING_NAME=$(grep -A5 "orgID: \"$ORG_ID\"" "$CONFIG_FILE" 2>/dev/null | grep -oP 'name:\s*"\K[^"]*' || true)

ACCOUNT_NAME=""
if [ -n "$EXISTING_NAME" ]; then
    echo "  Account exists with name: \"$EXISTING_NAME\" (name will be kept)"
else
    echo "[5/6] New account detected."
    echo "  Enter a name for this account (for your reference only):"
    read -r ACCOUNT_NAME
    if [ -z "$ACCOUNT_NAME" ]; then
        echo "ERROR: account name cannot be empty for new accounts" >&2
        rm -f "$TMPFILE"
        exit 1
    fi
    echo "  Name: \"$ACCOUNT_NAME\""
fi

# Step 5/6: Run the updater
echo "[6/6] Updating config..."
if [ -n "$ACCOUNT_NAME" ]; then
    python3 "$SCRIPT_DIR/add_account.py" "$TMPFILE" "$SESSION_KEY" "$PROXIES_FILE" "$CONFIG_FILE" "$ACCOUNT_NAME"
else
    python3 "$SCRIPT_DIR/add_account.py" "$TMPFILE" "$SESSION_KEY" "$PROXIES_FILE" "$CONFIG_FILE"
fi
RESULT=$?
rm -f "$TMPFILE"

if [ $RESULT -ne 0 ]; then
    echo "ERROR: parsing/updating failed" >&2
    exit 1
fi

echo ""
echo "=== Done ==="
echo "Restart to apply:"
echo "  pkill -f './claude2api'; cd /home/art/code/claude2api && ./claude2api"
