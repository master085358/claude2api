#!/usr/bin/env bash
# Add/update a claude2api account from a cURL dump in the clipboard.
#
#   ./tools/add-account.sh                      # interactive: asks for name if new
#   ./tools/add-account.sh myname               # name preset
#   ./tools/add-account.sh myname sk-ant-sid... # name + key (when Chrome dropped cookies)
#
# Source in Chrome: DevTools -> Network -> /completion request
#                   -> right-click -> Copy -> Copy as cURL

set -euo pipefail

ROOT="/home/art/code/claude2api"
CONFIG_FILE="$ROOT/config.yaml"
PROXIES_FILE="/home/art/.my-sys-env/proxies.txt"

NAME="${1:-}"
KEY_OVERRIDE="${2:-}"

[ -f "$CONFIG_FILE" ]  || { echo "ERROR: $CONFIG_FILE not found" >&2; exit 1; }
[ -f "$PROXIES_FILE" ] || { echo "ERROR: $PROXIES_FILE not found" >&2; exit 1; }

echo "=== Add/Update Account ==="

# --- 1. clipboard ---
[ -n "${DISPLAY:-}" ] || export DISPLAY=":0"
CLIPBOARD="$(xclip -selection clipboard -o 2>/dev/null || true)"
[ -n "$CLIPBOARD" ] || { echo "ERROR: clipboard empty. Copy as cURL first." >&2; exit 1; }
echo "[1] Clipboard: ${#CLIPBOARD} chars"

# --- 2. orgID ---
ORG_ID="$(printf '%s' "$CLIPBOARD" | grep -oP '/organizations/\K[a-f0-9\-]{36}(?=/)' | head -1 || true)"
[ -n "$ORG_ID" ] || { echo "ERROR: no /organizations/<uuid>/ in clipboard" >&2; exit 1; }
echo "[2] OrgID: $ORG_ID"

# --- 3. sessionKey: clipboard -> arg -> prompt ---
SK="$(printf '%s' "$CLIPBOARD" | grep -oP 'sessionKey=\K[^;\s"'"'"']+' | head -1 || true)"
if [ -z "$SK" ] && [ -n "$KEY_OVERRIDE" ]; then
    SK="$KEY_OVERRIDE"
    echo "[3] sessionKey: from argument"
fi
if [ -z "$SK" ]; then
    echo "[3] sessionKey NOT in clipboard (Chrome stripped the Cookie header)."
    echo "    Get it: DevTools -> Application -> Cookies -> https://claude.ai -> sessionKey -> Value"
    printf "    Paste sessionKey: "
    read -r SK
    [ -n "$SK" ] || { echo "ERROR: empty sessionKey" >&2; exit 1; }
fi
echo "    key: ${SK:0:36}..."

# --- 4. name: existing in config -> reuse; otherwise prompt ---
EXISTING_NAME="$(grep -A8 "orgID: \"$ORG_ID\"" "$CONFIG_FILE" 2>/dev/null \
    | grep -oP '^\s*name:\s*"\K[^"]*' | head -1 || true)"
if [ -n "$EXISTING_NAME" ]; then
    NAME="$EXISTING_NAME"
    echo "[4] Existing account: \"$NAME\" -> UPDATE"
elif [ -n "$NAME" ]; then
    echo "[4] New account: \"$NAME\" -> ADD"
else
    printf "[4] New account. Enter name: "
    read -r NAME
    [ -n "$NAME" ] || { echo "ERROR: empty name" >&2; exit 1; }
fi

# --- 5. apply ---
TMPFILE="$(mktemp /tmp/claude2api_XXXXXX)"
printf '%s' "$CLIPBOARD" > "$TMPFILE"
set +e
python3 "$ROOT/tools/add_account.py" "$TMPFILE" "$PROXIES_FILE" "$CONFIG_FILE" "$NAME" "${SK:-}"
RESULT=$?
set -e
rm -f "$TMPFILE"

[ "$RESULT" -eq 0 ] || { echo "ERROR: add_account.py exited with $RESULT" >&2; exit "$RESULT"; }

echo ""
echo "Restart to apply:"
echo "  pkill -f './claude2api'; cd $ROOT && ./claude2api"
