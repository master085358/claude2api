#!/usr/bin/env python3
"""Parse a browser fetch() request from a file and extract claude2api config."""
import sys
import re
import json


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_clipboard.py <file>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        print(f"ERROR: Cannot read file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Input: {len(text)} chars")

    # Find all fetch URLs
    url_pattern = r'fetch\("([^"]+)"'
    urls = re.findall(url_pattern, text)
    print(f"  Found {len(urls)} fetch calls")

    target_url = None
    for u in urls:
        if "/completion" in u and "chat_conversations" in u:
            target_url = u
            break

    if not target_url:
        print("\nERROR: No /completion fetch found in clipboard.")
        print("Copy from DevTools: Network tab > right-click request > Copy > Copy as fetch")
        sys.exit(1)

    print(f"  Target: {target_url[:120]}")

    # Extract org ID
    org_match = re.search(r"/organizations/([a-f0-9-]+)/", target_url)
    org_id = org_match.group(1) if org_match else ""
    print(f"  OrgID: {org_id}")

    # Locate the fetch call
    fetch_start = text.find('fetch("' + target_url + '"')
    if fetch_start == -1:
        print("ERROR: Cannot locate fetch call in text")
        sys.exit(1)

    chunk = text[fetch_start:]

    # Extract headers via brace matching
    headers = {}
    hm = re.search(r'"headers":\s*\{', chunk)
    if hm:
        start = hm.end()
        depth = 1
        i = start
        while i < len(chunk) and depth > 0:
            if chunk[i] == "{":
                depth += 1
            elif chunk[i] == "}":
                depth -= 1
            i += 1
        headers_str = chunk[hm.start() + len('"headers":'):i]
        try:
            headers = json.loads(headers_str)
            print(f"  Headers: {len(headers)} entries")
        except json.JSONDecodeError:
            for m in re.finditer(r'"([^"]+)":\s*"([^"]*)"', headers_str):
                headers[m.group(1)] = m.group(2)
            print(f"  Headers (regex fallback): {len(headers)} entries")
    else:
        print("  WARNING: no headers found")

    # Extract body
    body = {}
    bm = re.search(r'"body":\s*"', chunk)
    if bm:
        body_start = bm.end()
        i = body_start
        while i < len(chunk):
            if chunk[i] == "\\" and i + 1 < len(chunk):
                i += 2
            elif chunk[i] == '"':
                break
            else:
                i += 1
        body_raw = chunk[body_start:i]
        body_raw = body_raw.replace('\\"', '"').replace("\\\\", "\\")
        try:
            body = json.loads(body_raw)
            print(f"  Body: {len(body)} keys")
        except json.JSONDecodeError as e:
            print(f"  WARNING: body parse error: {e}")
            print(f"  Raw: {body_raw[:150]}")
    else:
        print("  WARNING: no body found")

    model = body.get("model", "claude-sonnet-5")
    effort = body.get("effort", "medium")
    thinking_mode = body.get("thinking_mode", "auto")
    timezone = body.get("timezone", "UTC")
    locale = body.get("locale", "en-US")
    rendering_mode = body.get("rendering_mode", "messages")
    tools = body.get("tools", [])

    print(f"  Model: {model}")
    print(f"  Effort: {effort}")
    print(f"  Thinking: {thinking_mode}")
    print(f"  Timezone: {timezone}")
    print(f"  Locale: {locale}")
    print(f"  Tools: {len(tools)}")

    output = {
        "orgID": org_id,
        "model": model,
        "effort": effort,
        "thinking_mode": thinking_mode,
        "timezone": timezone,
        "locale": locale,
        "rendering_mode": rendering_mode,
        "headers": {k: v for k, v in headers.items()
                    if k.startswith("anthropic-") or k == "accept-language"},
        "tools_count": len(tools),
    }

    print(f"\n[6/6] Result:")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()