#!/usr/bin/env python3
"""
Add/update account from cURL clipboard data (DevTools > Copy as cURL).
Extracts: orgID, sessionKey, model, device-id, User-Agent.

Usage: add_account.py <curl_file> <proxies_file> <config_file> [name]
"""
import sys
import re


def detect_country(proxy_url):
    m = re.search(r'-(\w{2})\.nexorcdn\.com', proxy_url)
    return m.group(1).lower() if m else "unknown"


def get_proxies_by_country(proxies_file):
    with open(proxies_file, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    by_country = {}
    for p in proxies:
        by_country.setdefault(detect_country(p), []).append(p)
    return by_country


def pick_proxy(proxies_file, used_proxies, preferred_country=None):
    by_country = get_proxies_by_country(proxies_file)
    if preferred_country and preferred_country in by_country:
        for p in by_country[preferred_country]:
            if p not in used_proxies:
                return p, preferred_country
    all_proxies = []
    for cp in by_country.values():
        all_proxies.extend(cp)
    for p in all_proxies:
        if p not in used_proxies:
            return p, detect_country(p)
    if preferred_country and preferred_country in by_country:
        pool = by_country[preferred_country]
    else:
        pool = all_proxies
    if pool:
        idx = len(used_proxies) % len(pool)
        return pool[idx], detect_country(pool[idx])
    return "", "unknown"


def extract_from_curl(text):
    """Extract all fields from cURL command."""
    result = {}

    # sessionKey from Cookie header
    m = re.search(r"Cookie:\s*[^'\"]*sessionKey=([^;'\"]+)", text)
    if not m:
        m = re.search(r"-b\s+['\"]sessionKey=([^;'\"]+)", text)
    if not m:
        m = re.search(r'(sk-ant-sid[^\s"\',;\\]+)', text)
    result["sessionKey"] = m.group(1) if m else None

    # orgID
    m = re.search(r'/organizations/([a-f0-9-]+)/', text)
    result["orgID"] = m.group(1) if m else None

    # User-Agent
    m = re.search(r"User-Agent:\s*([^'\"\\]+)", text)
    if not m:
        m = re.search(r"-A\s+['\"]([^'\"]+)", text)
    result["userAgent"] = m.group(1).strip() if m else ""

    # anthropic-device-id
    m = re.search(r"anthropic-device-id:\s*([a-f0-9-]+)", text)
    result["deviceID"] = m.group(1) if m else None

    # model
    m = re.search(r'"model":\s*"([^"]+)"', text)
    result["model"] = m.group(1) if m else None

    return result


def find_session_by_orgid(content, org_id):
    blocks = re.split(r'(?=\s*- sessionKey:)', content)
    for block in blocks:
        if f'orgID: "{org_id}"' in block:
            name_m = re.search(r'name:\s*"([^"]*)"', block)
            country_m = re.search(r'proxyCountry:\s*"([^"]*)"', block)
            return True, name_m.group(1) if name_m else "", country_m.group(1) if country_m else ""
    return False, "", ""


def update_session(content, org_id, session_key, proxy, country, user_agent):
    lines = content.split("\n")
    result = []
    in_target = False
    for line in lines:
        if f'orgID: "{org_id}"' in line:
            in_target = True
            result.append(line)
            continue
        if in_target:
            if re.match(r'\s*sessionKey:', line):
                result.append(f'  - sessionKey: "{session_key}"')
            elif re.match(r'\s*userAgent:', line):
                result.append(f'    userAgent: "{user_agent}"')
            elif re.match(r'\s*proxyCountry:', line):
                result.append(f'    proxyCountry: "{country}"')
            elif re.match(r'\s*proxy:', line):
                result.append(f'    proxy: "{proxy}"')
                in_target = False
            elif re.match(r'\s*- sessionKey:', line) or (line.strip() and not line.startswith(' ') and not line.startswith('\t')):
                in_target = False
                result.append(line)
            else:
                result.append(line)
        else:
            result.append(line)
    return "\n".join(result)


def add_session(content, org_id, session_key, proxy, name, country, user_agent):
    new_block = f'  - sessionKey: "{session_key}"\n    orgID: "{org_id}"\n    cookie: ""\n    name: "{name}"\n    userAgent: "{user_agent}"\n    proxyCountry: "{country}"\n    proxy: "{proxy}"\n'
    lines = content.split("\n")
    insert_idx = None
    in_sessions = False
    for i, line in enumerate(lines):
        if line.startswith("sessions:"):
            in_sessions = True
            continue
        if in_sessions:
            if line.strip() and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("-"):
                insert_idx = i
                break
    if insert_idx is None:
        insert_idx = len(lines)
    lines.insert(insert_idx, new_block.rstrip())
    return "\n".join(lines)


def main():
    if len(sys.argv) < 4:
        print("Usage: add_account.py <curl_file> <proxies_file> <config_file> [name]")
        sys.exit(1)

    curl_file = sys.argv[1]
    proxies_file = sys.argv[2]
    config_file = sys.argv[3]
    account_name = sys.argv[4] if len(sys.argv) > 4 else None

    with open(curl_file, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    print(f"  Input: {len(text)} chars")

    data = extract_from_curl(text)

    if not data["sessionKey"]:
        print("ERROR: sessionKey not found in cURL data.")
        print("  Make sure 'Copy as cURL' includes cookies.")
        print("  DevTools > Network > right-click > Copy > Copy as cURL")
        sys.exit(1)

    if not data["orgID"]:
        print("ERROR: no orgID found in cURL URL")
        sys.exit(1)

    print(f"  SessionKey: {data['sessionKey'][:40]}...")
    print(f"  OrgID: {data['orgID']}")
    print(f"  UserAgent: {data['userAgent'][:60]}...")
    if data["deviceID"]:
        print(f"  DeviceID: {data['deviceID']}")
    if data["model"]:
        print(f"  Model: {data['model']}")

    with open(config_file, "r") as f:
        content = f.read()

    used_proxies = re.findall(r'proxy:\s*"([^"]+)"', content)
    found, existing_name, existing_country = find_session_by_orgid(content, data["orgID"])

    if found:
        print(f"\n  \"{existing_name}\" EXISTS -> UPDATING (country: {existing_country})")
        proxy, country = pick_proxy(proxies_file, [p for p in used_proxies if p], existing_country)
        content = update_session(content, data["orgID"], data["sessionKey"], proxy, country, data["userAgent"])
        display_name = existing_name
    else:
        if not account_name:
            print("\nERROR: New account but no name provided.")
            sys.exit(2)
        proxy, country = pick_proxy(proxies_file, used_proxies)
        content = add_session(content, data["orgID"], data["sessionKey"], proxy, account_name, country, data["userAgent"])
        display_name = account_name
        print(f"\n  \"{account_name}\" -> ADDING")

    with open(config_file, "w") as f:
        f.write(content)

    print(f"\n  Name:    {display_name}")
    print(f"  OrgID:   {data['orgID']}")
    print(f"  Country: {country}")
    print(f"  Key:     {data['sessionKey'][:40]}...")
    print(f"  UA:      {data['userAgent'][:50]}...")
    print(f"  Proxy:   ...{proxy[-40:]}")


if __name__ == "__main__":
    main()
