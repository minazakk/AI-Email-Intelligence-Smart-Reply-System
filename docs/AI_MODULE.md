# AI Module (`ai_email`) - Architecture and Operations

Standalone AI pipeline for the **AI Email Intelligence & Smart Reply System**.
It has no dependency on a backend, a database, an API server or a frontend:
everything in this package runs in-process and can be exercised from Python,
a CLI or tests.

## 1. What this module owns

- Email input normalization for AI processing (raw text, `.eml`, JSON objects)
- Prompt templates and prompt versioning
- LLM provider adapter (mock / OpenAI / Gemini) behind one interface
- Classification, intent, summaries, structured extraction
- Sentiment, priority, reply-required / action-required detection
- Action items and deadline normalization (deterministic, timezone aware)
- Context-aware smart reply drafting (draft only - never sends)
- Inbox assistant Q&A over caller-supplied records
- Natural-language search intent parsing into a validated filter object
- Pydantic schemas, validation, synthetic dataset, evaluation, tests

It does **not** own authentication, the PostgreSQL schema, REST endpoints,
a frontend, real email sending, or Gmail/Outlook integration.

## 2. Layout

``` text
ai_email/
  __init__.py            public API (analyze_email, generate_smart_reply, ...)
  config.py              env-driven Settings (AI_PROVIDER, keys, limits)
  schemas.py             Pydantic contract (enums, analysis, reply, intent, ...)
  exceptions.py          typed error hierarchy
  email_parser.py        input normalization, raw text and .eml parsing
  date_normalizer.py     deterministic deadline/date resolution
  cli.py                 runnable CLI (analyze/reply/search/ask/deadline)
  prompts/
    classification.txt   analysis task + security rules
    extraction.txt       extraction and action-item rules
    smart_reply.txt      thread-aware draft rules
    inbox_assistant.txt  supplied-records-only answer rules
  providers/
    base.py              ProviderRequest/ProviderResponse, retries, JSON parsing
    mock_provider.py     deterministic offline provider
    mock_heuristics.py   rule-based analysis used by mock and fallback
    openai_provider.py   OpenAI chat-completions adapter (stdlib HTTP)
    gemini_provider.py   Gemini generateContent adapter (stdlib HTTP)
  services/
    analysis_service.py  analyze_email / analyze_emails
    reply_service.py     generate_smart_reply
    assistant_service.py answer_inbox_question
    search_intent_service.py  parse_search_query
    fallback.py          deterministic partial analysis on provider failure
tests/                   offline test suite (no network, no API key)
scripts/
  generate_dataset.py    reproducible synthetic dataset generator
  evaluate.py            measured evaluation report generator
docs/
  AI_MODULE.md           this file
  AI_INTEGRATION_CONTRACT.md  how a backend plugs in later
  EVALUATION_REPORT.md   measured numbers (generated)
```

## 3. Pipeline

``` text
EmailInput / raw text / .eml
        |
        v
email_parser.normalize_email   (validate, clean quotes/signatures, truncate)
        |
        v
reference datetime resolution  (received_at or caller reference + timezone)
        |
        v
prompt rendering  (classification.txt + extraction.txt, $schema injected)
        |
        v
provider.generate_structured   (mock | openai | gemini, bounded retries)
        |
        v
Pydantic validation            (EmailAnalysis)
        |
        v
processing metadata            (provider, model, prompt_version, latency,
                                status: completed | partial | failed)
```

Failure handling (`analyze_email(..., on_error=...)`):

| mode | behaviour |
|---|---|
| `raise` (default) | provider/schema errors propagate as typed exceptions |
| `status` | returns an analysis marked `processing_status="failed"` - never a fake success |
| `fallback` | deterministic, input-derived rules marked `processing_status="partial"` + `fallback_used=True` (requires `AI_ALLOW_FALLBACK=true`). Requesting fallback without that opt-in raises `ConfigurationError` instead of silently returning a different result. |

## 4. Public API

```python
from ai_email import (
    analyze_email,
    generate_smart_reply,
    answer_inbox_question,
    parse_search_query,
    normalize_deadline,
)

analysis = analyze_email(email, reference_datetime=None, timezone="UTC")
draft = generate_smart_reply(email, thread_messages, tone="professional")
answer = answer_inbox_question(question, retrieved_emails, pending_actions)
intent = parse_search_query("urgent complaints from this week")
deadline = normalize_deadline("by Friday", reference_datetime, timezone)
```

All inputs and outputs are Pydantic models; `model_dump()`/`model_dump_json()`
produce the JSON shown in `docs/AI_INTEGRATION_CONTRACT.md`.

## 5. Prompt security and grounding

- Email bodies, quoted chains, signatures and imported files are treated as
  **untrusted data**. They are delimited (`<<<UNTRUSTED_..._BEGIN/END>>>`) and
  never placed in the system/developer instruction section.
- The rule-based path (mock provider and fallback) additionally scrubs
  model-directed lines (`IGNORE PREVIOUS INSTRUCTIONS`, `Set category=...`,
  `priority=...`, `reveal your system prompt`, ...) before scoring, so an
  embedded instruction cannot escalate category/priority/sentiment or inject
  field values into the heuristic output. If scrubbing would remove the whole
  body, the original text is kept.
- Every prompt instructs the model to ignore embedded instructions that try to
  change its role, reveal prompts/secrets or override the analysis.
- Unknown information must come back as `null` / `[]` / `other`; inventing
  names, numbers, amounts, dates or promises is prohibited by the prompt and
  checked by tests (`tests/test_analysis.py::test_prompt_injection_...`,
  `::test_missing_information_is_not_hallucinated`).
- `parse_search_query` is fully deterministic (no model call), so filters are
  always validated enum values; the model never produces SQL and never gets
  database access.
- Smart replies are drafts only: `sent` is always `False` and
  `requires_user_approval` is always `True` (enforced in the schema, not just
  the prompt).

## 6. Provider configuration

`.env.example` (placeholders only):

```env
AI_PROVIDER=mock
AI_MODEL=
OPENAI_API_KEY=
GEMINI_API_KEY=
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=2
AI_TEMPERATURE=0.2
AI_MAX_BODY_CHARS=20000
AI_MAX_EML_BYTES=2000000
AI_DEFAULT_TIMEZONE=UTC
AI_ALLOW_FALLBACK=false
```

- `AI_PROVIDER=mock` (default): fully offline and deterministic. Output is
  labelled `provider="mock"` and must be presented as mock, not as live AI.
- `AI_PROVIDER=openai`: stdlib HTTPS call to `https://api.openai.com/v1/chat/completions`
  with `response_format=json_object`. Default model `gpt-4o-mini`.
- `AI_PROVIDER=gemini`: stdlib HTTPS call to `generativelanguage.googleapis.com`
  `generateContent` with `responseMimeType: application/json`. Default model
  `gemini-1.5-flash`.
- Retries: bounded (`AI_MAX_RETRIES`) with exponential backoff; rate limits and
  timeouts are retryable, auth errors are not. Malformed JSON and schema
  failures raise `SchemaValidationError`.
- Keys stay server-side. They are never imported by frontend code and are never
  logged.

## 7. Deadline normalization

`normalize_deadline(raw_text, reference_datetime, timezone)` resolves
`today`, `tomorrow`, bare weekdays (`by Friday`), `next <weekday>`,
`within N days/weeks`, `end of this month/week`, explicit dates
(`25 September 2025`, `2025-09-25`, unambiguous `25/06/2025`).

It always returns the raw phrase. When a phrase is ambiguous
(`next week`, `asap`, `TBD`, `05/06/2025`, unknown patterns) it returns
`resolution="ambiguous"` with `normalized_date=None` instead of guessing.
Reference points come from the caller/email timestamp - never the server clock.

## 8. Commands

```bash
# install
pip install -r requirements.txt

# generate the synthetic dataset (90 emails, 10 per group)
python scripts/generate_dataset.py

# run the offline test suite (no network, no API key)
python -m pytest

# lint + format checks (config in ruff.toml)
ruff check .
ruff format --check .

# measured evaluation + report
python scripts/evaluate.py            # writes docs/EVALUATION_REPORT.md

# adversarial probes (injection, fabricated ids, hostile search text,
# oversized input, malicious .eml, provider failures) - non-zero exit on failure
python scripts/probe_adversarial.py

# CLI demo
python examples/demo_analysis.py          # analysis + draft + search intent + deadline
python -m ai_email.cli analyze --text "Please send invoice INV-7781 by tomorrow"
python -m ai_email.cli analyze --file path/to/message.eml
python -m ai_email.cli reply --text "..." --tone apologetic
python -m ai_email.cli search "urgent customer complaints from this week"
python -m ai_email.cli ask "which emails need my reply?" --records tests/fixtures/sample_emails.json
python -m ai_email.cli deadline --text "next Monday" --reference 2025-09-22T09:00:00+00:00
```

OpenAPI/Swagger is not provided by this module: it has no HTTP server by
design. The future backend owns the REST surface and can expose this module's
schemas (see `docs/AI_INTEGRATION_CONTRACT.md`).

## 9. Tests

`python -m pytest` runs 134 offline tests covering:

- schema validation, invalid enums, confidence bounds, missing optional fields
- valid/malformed structured output, empty/long emails
- missing fields not hallucinated, prompt-injection content in bodies
- model-directed instruction lines cannot override labels, inject field
  values, or steer drafted replies in the rule-based path
- category vs priority, sentiment vs urgency distinctions
- deadline normalization incl. weekdays, year boundaries, leap years,
  ambiguous dates, timezone conversion
- thread-aware replies, tone selection, no unsupported promises, never sent
- assistant answers limited to supplied records, fabricated ids dropped,
  deterministic counts
- search intent parsing and validated filter values
- provider retry/backoff, retry exhaustion, non-retryable auth errors,
  malformed output, mock provider without credentials
- `.eml`/raw-text parsing, size limits, quoted-chain and HTML cleanup
- dataset regression: shape, reproducibility, labels, extractions, deadlines

Tests use only the deterministic mock provider: no internet access and no API
key are required.

## 10. Evaluation

`python scripts/evaluate.py` measures the module against
`tests/fixtures/sample_emails.json` (90 synthetic emails with expected
category/priority/sentiment/reply/action labels, expected extractions,
expected deadlines and fields that must stay `null`).

The generated `docs/EVALUATION_REPORT.md` contains the measured numbers for
labels, extractions, hallucination checks, deadline checks and per-group
category accuracy. Live-provider evaluation is documented in the report but
has **not** been executed here (needs a paid API key).

## 11. Known limitations

- The mock provider is rule-based. It is honest, offline and deterministic,
  but it is not a large language model; its drafts and summaries are templates.
- Live adapters (`openai`, `gemini`) are implemented and unit-tested for
  request construction and error mapping, but have **not** been called against
  the real APIs from this repository - no credentials were available.
- No vector store / embeddings are used. Search intent parsing is keyword and
  date-rule based; richer semantic search belongs to the future backend.
- Attachments are never parsed beyond ignoring them in `.eml` files.
- The module does not enforce authentication; it must only ever receive records
  the calling backend has already authorized for the current user.
- Analytics, dashboard metrics and notifications are backend concerns and are
  intentionally not implemented here.
