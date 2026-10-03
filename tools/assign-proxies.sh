#!/usr/bin/env bash
# Assign proxies from proxies.txt to sessions in config.yaml
# Usage: ./tools/assign-proxies.sh [proxies_file]
# Default proxies file: /home/art/.my-sys-env/proxies.txt

CONFIG_FILE="/home/art/code/claude2api/config.yaml"
PROXIES_FILE="${1:-/home/art/.my-sys-env/proxies.txt}"

echo "[1/4] Checking files..."
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: $CONFIG_FILE not found" >&2
    exit 1
fi
if [ ! -f "$PROXIES_FILE" ]; then
    echo "ERROR: proxies file not found: $PROXIES_FILE" >&2
    exit 1
fi
echo "  Config: $CONFIG_FILE"
echo "  Proxies: $PROXIES_FILE"

echo "[2/4] Reading proxies..."
mapfile -t PROXIES < <(grep -v '^\s*$' "$PROXIES_FILE")
PROXY_COUNT=${#PROXIES[@]}
echo "  Found $PROXY_COUNT proxies"

if [ "$PROXY_COUNT" -eq 0 ]; then
    echo "ERROR: no proxies in file" >&2
    exit 1
fi

echo "[3/4] Counting sessions in config..."
SESSION_COUNT=$(grep -c 'sessionKey:' "$CONFIG_FILE" || true)
echo "  Found $SESSION_COUNT sessions"

if [ "$SESSION_COUNT" -eq 0 ]; then
    echo "ERROR: no sessions in config" >&2
    exit 1
fi

echo "[4/4] Assigning proxies round-robin..."
python3 - "$CONFIG_FILE" "$PROXIES_FILE" << 'PYEOF'
import sys
import re

config_path = sys.argv[1]
proxies_path = sys.argv[2]

with open(proxies_path, "r") as f:
    proxies = [line.strip() for line in f if line.strip()]

with open(config_path, "r") as f:
    content = f.read()

# Find all session blocks and assign proxies round-robin
proxy_idx = 0
lines = content.split("\n")
result = []
in_session = False

for i, line in enumerate(lines):
    if re.match(r'\s*- sessionKey:', line):
        # If we were in a previous session without proxy, add it
        if in_session:
            proxy = proxies[proxy_idx % len(proxies)]
            result.append(f'    proxy: "{proxy}"')
            proxy_idx += 1
        in_session = True
        result.append(line)
        continue

    if in_session:
        if re.match(r'\s*proxy:', line):
            # Replace existing proxy
            proxy = proxies[proxy_idx % len(proxies)]
            result.append(f'    proxy: "{proxy}"')
            proxy_idx += 1
            in_session = False
            continue
        elif re.match(r'\s*(cookie|orgID):', line):
            result.append(line)
            continue
        elif not line.startswith(' ') and line.strip() and not re.match(r'\s*- sessionKey:', line):
            # Top-level key: end of session block, insert proxy
            proxy = proxies[proxy_idx % len(proxies)]
            result.append(f'    proxy: "{proxy}"')
            proxy_idx += 1
            in_session = False
            result.append(line)
            continue
        else:
            result.append(line)
            continue
    else:
        result.append(line)

# Handle last session if still open
if in_session:
    proxy = proxies[proxy_idx % len(proxies)]
    result.append(f'    proxy: "{proxy}"')
    proxy_idx += 1

output = "\n".join(result)

with open(config_path, "w") as f:
    f.write(output)

print(f"  Assigned {proxy_idx} proxies to sessions")
PYEOF

if [ $? -ne 0 ]; then
    echo "ERROR: assignment failed" >&2
    exit 1
fi

echo ""
echo "Done. Restart claude2api to apply."
