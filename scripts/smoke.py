import json
import sys
from pathlib import Path

# Allow `python scripts/smoke.py` from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ai_email

email = {
    "subject": "Refund request - order damaged",
    "sender": "Maria Lopez <maria.lopez@example.com>",
    "body": (
        "Hi, my order ORD-99321 arrived damaged and the box was broken. "
        "This is unacceptable. I want a refund of $149.99 within 3 days. "
        "Please confirm by Friday. My phone is +1 555 010 2233. Maria"
    ),
    "received_at": "2025-09-22T10:00:00+00:00",
}

analysis = ai_email.analyze_email(email, reference_datetime="2025-09-22T10:00:00+00:00")
print(json.dumps(analysis.model_dump(mode="json"), indent=2, default=str))
print("---")
reply = ai_email.generate_smart_reply(email, [], tone="apologetic")
print(reply.model_dump_json(indent=2))
print("---")
intent = ai_email.parse_search_query("show all urgent customer complaints from this week", "2025-09-22T10:00:00+00:00")
print(intent.model_dump_json(indent=2))
print("---")
answer = ai_email.answer_inbox_question(
    "Which emails need my reply?",
    [{"id": "e1", "subject": "Refund request", "sender": "maria@example.com", "reply_required": True}],
    reference_datetime="2025-09-22T10:00:00+00:00",
)
print(answer.model_dump_json(indent=2))
print("---")
print(ai_email.normalize_deadline("next Monday", "2025-09-22T10:00:00+00:00", "UTC"))
print(ai_email.normalize_deadline("sometime next week", "2025-09-22T10:00:00+00:00", "UTC"))
