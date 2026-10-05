"""Runnable demo: paste an email, get validated JSON analysis + a draft.

python examples/demo_analysis.py
python examples/demo_analysis.py --file path/to/message.eml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_email import (
    analyze_email,
    generate_smart_reply,
    normalize_deadline,
    parse_email_text,
    parse_eml,
    parse_search_query,
)

SAMPLE_EMAIL = {
    "subject": "Refund request - item arrived damaged",
    "sender": "Dana Brooks <dana.brooks@example.test>",
    "recipients": ["support@ourcorp.example"],
    "body": (
        "Hi, my order ORD-55210 arrived damaged and the box was crushed. "
        "I am disappointed and would like a refund of 89.50 USD within 3 days. "
        "Please confirm by Friday. My name is Dana Brooks."
    ),
    "received_at": "2025-09-22T09:00:00+00:00",
    "message_id": "msg-001",
}


def load_email(args: argparse.Namespace):
    if args.file:
        data = Path(args.file).read_bytes()
        if args.file.lower().endswith(".eml"):
            return parse_eml(data)
        return parse_email_text(data.decode("utf-8", errors="replace"))
    if args.text:
        return parse_email_text(args.text)
    return SAMPLE_EMAIL


def main() -> None:
    parser = argparse.ArgumentParser(description="AI email module demo")
    parser.add_argument("--file", help=".eml or raw text file")
    parser.add_argument("--text", help="raw email text")
    parser.add_argument("--tone", default="professional")
    args = parser.parse_args()

    email = load_email(args)
    if isinstance(email, dict):
        received = email.get("received_at")
    else:
        received = email.received_at
    reference = received or "2025-09-22T09:00:00+00:00"

    analysis = analyze_email(email, reference_datetime=reference, timezone="UTC")
    print("=== ANALYSIS ===")
    print(json.dumps(analysis.model_dump(mode="json"), indent=2, default=str))

    draft = generate_smart_reply(email, [], tone=args.tone, reference_datetime=reference)
    print("\n=== SMART REPLY DRAFT (never sent) ===")
    print(json.dumps(draft.model_dump(mode="json"), indent=2, default=str))

    intent = parse_search_query("show urgent customer complaints from this week", reference)
    print("\n=== SEARCH INTENT ===")
    print(json.dumps(intent.model_dump(mode="json"), indent=2, default=str))

    deadline = normalize_deadline("next Monday", reference, "UTC")
    print("\n=== DEADLINE ===")
    print(json.dumps(deadline.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    main()
