import json
from pathlib import Path

import requests

# ----------------------------
# Editable constants
# ----------------------------
MAKE_MATCH_URL = "https://www.jjose.tech/match/make"
USERS_ALL_URL = "https://www.jjose.tech/users/all"
AUTH_BEARER_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJub2VsZ2VvcmdpMjRiY2QyM0BpaWl0a290dGF5YW0uYWMuaW4iLCJuYW1lIjoiTk9FTCBHRU9S"
    "R0kgLUlJSVRLIiwiaWF0IjoxNzcwOTk0MzU1LCJleHAiOjE3NzA5OTc5NTV9."
    "OoqjsOa4YVTcN4PPTlMRzlBax4eSfCsr7p-giwnq_Co"
)

# Pick users from users/all response by index.
PERSON1_EMAIL_INDEX = 0
MATCHER_EMAIL_INDEX = 1

# Keep as literal constant if you do not want this from leaderboard.
person2_email = "mishalsabu24bcs0214@iiitkottayam.ac.in"

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
        # Common response shapes.
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


def _pick_email(users_payload: object, index: int, field_name: str) -> str:
    users = _extract_users(users_payload)
    if not users:
        raise ValueError("No users found in users/all response.")

    if not (0 <= index < len(users)):
        raise IndexError(f"{field_name} index {index} out of range (0..{len(users) - 1}).")

    email = _extract_email(users[index])
    if not email:
        raise ValueError(f"Selected {field_name} user at index {index} has no valid email.")

    return email


def _get_users_all_json() -> object:
    response = requests.get(USERS_ALL_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    users_all_json = _get_users_all_json()

    person1_email = _pick_email(users_all_json, PERSON1_EMAIL_INDEX, "person1_email")
    matcher_email = _pick_email(users_all_json, MATCHER_EMAIL_INDEX, "matcher_email")

    payload = {
        "person1_email": person1_email,
        "person2_email": person2_email,
        "matcher_email": matcher_email,
    }

    print("Payload:")
    print(json.dumps(payload, indent=2))

    response = requests.post(MAKE_MATCH_URL, headers=HEADERS, json=payload, timeout=30)
    print("Status:", response.status_code)

    try:
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print("Response text:")
        print(response.text)


if __name__ == "__main__":
    main()
