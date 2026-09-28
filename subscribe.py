#!/usr/bin/env python3
"""Subscription bot logic for the Influencer Alpha Weekly.

Triggered by the subscribe.yml workflow when an issue is opened.
Reads ISSUE_TITLE / ISSUE_BODY from the environment, updates
subscribers.txt, and prints a JSON result for the workflow to act on.

Only the first email-like string in the body is ever used, and it is
only ever written to subscribers.txt -- untrusted input is never
executed or interpolated into shell commands.
"""
import json
import os
import re
import sys

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, "subscribers.txt")


def load_subscribers() -> list[str]:
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    with open(SUBSCRIBERS_FILE, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_subscribers(emails: list[str]) -> None:
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(emails) + ("\n" if emails else ""))


def main() -> None:
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")
    lowered = title.lower()
    found = EMAIL_RE.findall(body)
    email = found[0].lower() if found else None

    result = {"action": "none", "changed": False, "message": ""}

    if "unsubscribe" in lowered:
        if not email:
            result["message"] = (
                "I couldn't find an email address in the issue body. "
                "Please include the address you want to unsubscribe."
            )
        else:
            subs = load_subscribers()
            if email in [s.lower() for s in subs]:
                save_subscribers([s for s in subs if s.lower() != email])
                result.update(
                    action="unsubscribed", changed=True,
                    message=f"{email} has been unsubscribed. Sorry to see you go!",
                )
            else:
                result.update(
                    action="not_found",
                    message=f"{email} is not on the subscriber list.",
                )
    elif "subscribe" in lowered:
        if not email:
            result["message"] = (
                "I couldn't find an email address in the issue body. "
                "Please include your email so I can subscribe you."
            )
        else:
            subs = load_subscribers()
            if email in [s.lower() for s in subs]:
                result.update(
                    action="already",
                    message=f"{email} is already subscribed. You're all set!",
                )
            else:
                subs.append(email)
                save_subscribers(subs)
                result.update(
                    action="subscribed", changed=True,
                    message=(
                        f"\U0001f389 You're subscribed, {email}! "
                        "You'll receive the Influencer Alpha \u5468\u62a5 "
                        "every Sunday evening (Pacific Time)."
                    ),
                )
    else:
        result["message"] = (
            "This doesn't look like a subscribe/unsubscribe request. "
            "Open an issue titled 'Subscribe' (or 'Unsubscribe') and put "
            "your email address in the body."
        )

    print(json.dumps(result))


if __name__ == "__main__":
    sys.exit(main())
