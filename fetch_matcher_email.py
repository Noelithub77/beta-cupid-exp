import json
from datetime import datetime, timezone
from pathlib import Path

import requests

USERS_ALL_URL = "https://www.jjose.tech/users/all"
AUTH_BEARER_TOKEN = "See you in pairialo"
MATCHER_EMAIL_INDEX = 1
OUTPUT_FILE = Path("users_all.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://cupids-ledger.vercel.app/",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AUTH_BEARER_TOKEN}",
    "Origin": "https://cupids-ledger.vercel.app",
    "Sec-GPC": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
}


def _extract_users(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("users", "data", "result", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _extract_email(user: dict) -> str | None:
    direct = user.get("email")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for parent_key in ("user", "profile"):
        nested = user.get(parent_key)
        if isinstance(nested, dict):
            nested_email = nested.get("email")
            if isinstance(nested_email, str) and nested_email.strip():
                return nested_email.strip()

    return None


def _pick_matcher_email(users_payload: object, index: int) -> str:
    users = _extract_users(users_payload)
    if not users:
        raise ValueError("No users found in users/all response.")

    if not (0 <= index < len(users)):
        raise IndexError(f"MATCHER_EMAIL_INDEX {index} out of range (0..{len(users) - 1}).")

    email = _extract_email(users[index])
    if not email:
        raise ValueError(f"Selected matcher user at index {index} has no valid email.")

    return email


def main() -> None:
    response = requests.get(USERS_ALL_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    data = response.json()
    OUTPUT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    matcher_email = _pick_matcher_email(data, MATCHER_EMAIL_INDEX)
    ts = datetime.now(timezone.utc).isoformat()

    print(f"Saved users/all JSON to {OUTPUT_FILE.resolve()}")
    print(f"Fetched at: {ts}")
    print(f"matcher_email: {matcher_email}")


if __name__ == "__main__":
    main()
