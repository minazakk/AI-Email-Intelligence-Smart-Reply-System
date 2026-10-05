# AI Integration Contract

How a future backend connects to the standalone `ai_email` module.

**Boundary rule:** the module speaks plain validated Pydantic schemas only. It
has no database models, no ORM imports, no HTTP layer and no knowledge of
sessions or users. It must only ever receive data that the calling backend has
already authorized for the authenticated user.

## 1. Public callable functions

```python
from ai_email import (
    analyze_email,  # (email, reference_datetime=None, timezone="UTC", *, settings=None, provider=None, on_error="raise") -> EmailAnalysis
    analyze_emails,  # batch wrapper -> list[EmailAnalysis]
    generate_smart_reply,  # (email, thread_messages, tone="professional", business_context=None, *, length_preference=None, ...) -> SmartReplyResult
    answer_inbox_question,  # (question, retrieved_emails, pending_actions=None, reference_datetime=None, timezone="UTC", *, matched_count=None, ...) -> AssistantAnswer
    parse_search_query,  # (question, reference_datetime=None, timezone="UTC") -> EmailSearchIntent
    normalize_deadline,  # (raw_text, reference_datetime, timezone="UTC") -> NormalizedDeadline
)
```

Input helpers (no backend required):

```python
from ai_email import EmailInput, ThreadMessage, parse_email_text, parse_eml, normalize_email
```

## 2. Enums

| Enum | Values |
|---|---|
| `category` | `sales_inquiry`, `customer_complaint`, `support_request`, `meeting_request`, `invoice_payment`, `job_application`, `general_information`, `spam`, `urgent`, `other` |
| `priority` | `low`, `medium`, `high`, `critical` |
| `sentiment` | `positive`, `neutral`, `negative`, `angry`, `urgent` |
| `action_status` | `pending`, `in_progress`, `completed`, `dismissed` |
| `tone` | `professional`, `friendly`, `short`, `detailed`, `apologetic`, `formal` |
| `processing_status` | `pending`, `completed`, `partial`, `failed` |
| `read_state` (search) | `read`, `unread`, `any` |

Category = primary purpose. Priority = time sensitivity/impact. Sentiment =
expressed tone. They are independent: a complaint can be `high` priority with
`negative` sentiment without using the `urgent` category.

## 3. Input shape for an email

```json
{
  "subject": "Refund request",
  "sender": "Dana Brooks <dana.brooks@example.test>",
  "recipients": ["support@ourcorp.example"],
  "body": "Hi, my order ORD-55210 arrived damaged...",
  "received_at": "2025-09-22T09:00:00+00:00",
  "thread_id": "thread-17",
  "message_id": "msg-001",
  "is_read": false
}
```

`message_id`/`thread_id` are optional and pass through as `email_id`/
`thread_id` on the outputs so the backend can persist results.

## 4. Output shapes

### 4.1 `EmailAnalysis`

```json
{
  "category": "customer_complaint",
  "intent": "requesting_refund",
  "priority": "high",
  "priority_reason": "The customer reports a damaged order and asks for a response within 3 days.",
  "sentiment": "negative",
  "sentiment_confidence": 0.9,
  "reply_required": true,
  "action_required": true,
  "short_summary": "The customer reports a damaged order and requests a refund.",
  "detailed_summary": "Dana Brooks reports that order ORD-55210 arrived damaged...",
  "participants": ["Dana Brooks <dana.brooks@example.test>"],
  "extracted_information": {
    "customer_name": "Dana Brooks",
    "company": null,
    "phone_number": null,
    "email_address": "dana.brooks@example.test",
    "order_number": "ORD-55210",
    "invoice_number": null,
    "product": null,
    "amount": "89.50",
    "currency": "USD",
    "dates": [],
    "deadlines": [
      {"text": "within 3 days", "normalized_date": "2025-09-25"},
      {"text": "by Friday", "normalized_date": "2025-09-26"}
    ],
    "meeting_date": null,
    "location": null,
    "requested_action": "Please confirm the refund within 3 days."
  },
  "action_items": [
    {
      "description": "Please confirm the refund within 3 days.",
      "owner": null,
      "deadline_text": "by Friday",
      "due_date": "2025-09-26",
      "status": "pending",
      "source_email_id": "msg-001",
      "evidence": "Please confirm the refund within 3 days."
    }
  ],
  "key_points": ["..."],
  "unresolved_issues": [],
  "processing_metadata": {
    "provider": "mock",
    "model": "mock-model",
    "prompt_version": "1.0",
    "processing_status": "completed",
    "latency_ms": 3.2,
    "fallback_used": false,
    "error": null,
    "usage": {"prompt_tokens": 0, "completion_tokens": 0}
  },
  "email_id": "msg-001"
}
```

Unknown values are `null`/`[]` - never invented.

### 4.2 `SmartReplyResult`

```json
{
  "draft": "Hello Dana,\n\nThank you for your email...",
  "tone": "apologetic",
  "subject_line": "Re: Refund request",
  "warnings": ["The email mentions an amount - verify it before quoting it back."],
  "thread_id": "thread-17",
  "reply_to_message_id": "msg-001",
  "status": "draft",
  "requires_user_approval": true,
  "sent": false,
  "generated_at": null,
  "processing_metadata": {"provider": "mock", "processing_status": "completed", "...": "..."}
}
```

`sent` and `requires_user_approval` are enforced by the schema: the module can
never return an already-sent reply.

### 4.3 `EmailSearchIntent`

```json
{
  "categories": ["customer_complaint"],
  "priorities": ["high"],
  "sentiments": [],
  "reply_required": null,
  "action_required": null,
  "urgent": true,
  "read_state": "any",
  "keywords": [],
  "date_from": "2025-09-22",
  "date_to": "2025-09-22",
  "free_text": "urgent customer complaints from this week",
  "matched_rules": ["category:customer_complaint", "priority:high", "urgent:true", "date:this_week"]
}
```

The backend applies these fields with parameterized queries. The module never
produces SQL and never executes queries.

### 4.4 `AssistantAnswer`

```json
{
  "answer": "From the 2 record(s) supplied: ...",
  "scope": "supplied_records",
  "records_supplied": 2,
  "records_matched": 2,
  "referenced_email_ids": ["msg-001", "msg-014"],
  "out_of_scope": false,
  "follow_up_questions": ["Filter these records by category or date?"],
  "processing_metadata": {"provider": "mock", "processing_status": "completed"}
}
```

### 4.5 `NormalizedDeadline`

```json
{
  "raw_text": "by Friday",
  "normalized_date": "2025-09-26",
  "timezone": "UTC",
  "resolution": "resolved",
  "reason": null
}
```

`resolution` is `resolved` | `ambiguous` | `no_date`. Ambiguous phrases keep
the raw text with `normalized_date: null`.

## 5. How the backend supplies user-scoped data

1. Authenticate the request and resolve `user_id`.
2. Load the user's emails/threads from the database with a `WHERE user_id = ?`
   filter (parameterized).
3. Convert rows to the plain input schema above (or pass the stored
   `analysis` payload when re-analyzing).
4. Call the module. It performs no lookups of its own.

For the inbox assistant specifically:

```python
records = load_emails_for_user(user_id, limit=50)  # backend-owned query
intent = parse_search_query(question, now, "UTC")  # validated filters
matches = apply_filters(records, intent)  # backend-owned, parameterized
answer = answer_inbox_question(question, matches, pending_actions, now, matched_count=len(matches))
```

`records_supplied`/`records_matched` are recomputed and overwritten by the
module after the model answers, and any `referenced_email_ids` not present in
the supplied set are dropped and flagged with `out_of_scope=true`.

## 6. Persisting results

Suggested mapping (backend owns the schema):

| module field | storage advice |
|---|---|
| original email | store unchanged, separate table from analysis |
| `EmailAnalysis.*` | one row per analyzed email, keyed by `email_id` |
| `processing_metadata.processing_status` | index for retry/monitoring queues |
| `processing_metadata.fallback_used` / `error` | store for audit; show as "partial/failed", never as success |
| `action_items[]` | child rows; keep `status` under user control |
| `SmartReplyResult.draft` | store as a draft with status `pending_approval`; do not send |
| `EmailSearchIntent` | ephemeral - do not persist as executed SQL |
| `AssistantAnswer` | store per conversation turn if you keep assistant history |

The AI module keeps original email content and generated analysis separate;
do not overwrite the source email with model output.

## 7. Provider failures and partial results

| situation | what the module returns/raises | what the backend should do |
|---|---|---|
| provider timeout/rate limit/unavailable | raises `ProviderError` subclass (`on_error="raise"`) | store `processing_status="failed"` + error, offer retry |
| malformed JSON / schema mismatch | raises `SchemaValidationError` | store failed status; do not present as analyzed |
| `on_error="status"` | analysis with `processing_status="failed"` | persist as-is; UI shows an error state |
| `on_error="fallback"` + `AI_ALLOW_FALLBACK=true` | `processing_status="partial"`, `fallback_used=true` | persist as partial; label it as non-LLM rules output |
| `on_error="fallback"` without `AI_ALLOW_FALLBACK` | raises `ConfigurationError` | fix configuration (or use `on_error="status"`); do not catch it as a normal failure |
| live provider configured but key invalid | raises `ProviderAuthError` (never retryable) | surface configuration error in admin/logs only |

Never present `failed` or `partial` output as a completed AI analysis.

## 8. Smart reply approval flow (backend responsibility)

1. Call `generate_smart_reply(...)` and store the returned draft with
   `status="draft"`, `requires_user_approval=true`, `sent=false`.
2. Let the user edit the draft; never overwrite an edited draft by
   regenerating silently (regeneration is an explicit user action).
3. Approve/reject explicitly. Only a separate, backend-owned "send" action -
   outside this module - may ever dispatch an email.
4. The module contains no send capability and no SMTP/API send call.

## 9. Authentication and authorization

The module does **not** implement authentication and cannot enforce it. The
backend must:

- authenticate users and apply role checks (user/admin) before any call,
- scope every email/thread/action/notification passed to the module by
  `user_id`,
- never pass another user's records to `answer_inbox_question`,
- keep AI keys server-side (env vars) and out of responses/logs.

## 10. Versioning

- `ai_email.__version__` and `processing_metadata.prompt_version` identify the
  module and prompt revision that produced an analysis.
- Schemas are additive: new optional fields may appear; existing enum values
  are not removed without a major version bump.
- `docs/AI_MODULE.md` documents operations; update both when the contract
  changes.
