#!/usr/bin/env bash
# Parse a browser fetch() request from clipboard and generate claude2api config
# Usage: ./tools/parse-clipboard.sh
# Requires: xclip, python3, proxy configured in config.yaml

CONFIG_FILE="/home/art/code/claude2api/config.yaml"

echo "[1/6] Checking proxy configuration..."
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: config.yaml not found at $CONFIG_FILE" >&2
    exit 1
fi

PROXY=$(grep -oP '^\s*proxy:\s*"\K[^"]+' "$CONFIG_FILE" 2>/dev/null || true)
if [ -z "$PROXY" ]; then
    echo "ERROR: No proxy configured in $CONFIG_FILE" >&2
    echo "  This utility REQUIRES a proxy to be set." >&2
    exit 1
fi
echo "  OK: proxy configured: ${PROXY:0:30}..."

echo "[2/6] Checking xclip..."
if ! command -v xclip >/dev/null 2>&1; then
    echo "ERROR: xclip not found. Install: sudo apt install xclip" >&2
    exit 1
fi
echo "  OK: $(which xclip)"

echo "[3/6] Checking DISPLAY..."
if [ -z "${DISPLAY:-}" ]; then
    export DISPLAY=":0"
    echo "  Auto-set DISPLAY=$DISPLAY"
else
    echo "  OK: DISPLAY=$DISPLAY"
fi

echo "[4/6] Reading clipboard..."
CLIPBOARD="$(xclip -selection clipboard -o 2>&1)" || true

if [ -z "$CLIPBOARD" ]; then
    echo "ERROR: clipboard is empty or xclip failed." >&2
    echo "  Copy a request from DevTools > Network > right-click > Copy as fetch" >&2
    exit 1
fi

CLIP_LEN=${#CLIPBOARD}
echo "  OK: $CLIP_LEN chars"
echo "  Preview: ${CLIPBOARD:0:120}..."
echo ""

echo "[5/6] Parsing..."

TMPFILE=$(mktemp /tmp/clipboard_XXXXXX.txt)
printf '%s' "$CLIPBOARD" > "$TMPFILE"

python3 /home/art/code/claude2api/tools/parse_clipboard.py "$TMPFILE"
PYTHON_EXIT=$?
rm -f "$TMPFILE"

if [ $PYTHON_EXIT -ne 0 ]; then
    echo "ERROR: parsing failed (exit $PYTHON_EXIT)" >&2
    exit 1
fi

echo ""
echo "Done."