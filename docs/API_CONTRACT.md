# API Contract

Base URL for every versioned route: **`/api/v1`**
Interactive documentation (disabled in production): `GET /docs` · `GET /redoc`
Machine-readable schema: `GET /openapi.json` (OpenAPI 3.x)

---

## 1. Authentication

Two token types are issued by `POST /api/v1/auth/signup` and `POST /api/v1/auth/login`:

| Token | Where it lives | Lifetime | Purpose |
|---|---|---|---|
| `access_token` | Client memory / header | `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30 min) | Sent as `Authorization: Bearer <token>` on every request |
| `refresh_token` | HttpOnly cookie `refresh_token` (path `/api/v1/auth`) **and** response body | `REFRESH_TOKEN_EXPIRE_DAYS` (default 14 days) | Exchanged at `POST /api/v1/auth/refresh` for a new pair |

Rules:

* Refresh tokens are **rotating and single-use**. The old token is revoked the moment a
  new one is minted; replaying it returns `401 refresh_invalid`.
* Every access token carries its session id in the `jti` claim (`s<id>`). Each
  authenticated request checks that the session is still alive, so revoking a session
  kills the matching access tokens immediately — `401 session_revoked`. The same applies
  to `POST /auth/password/change` and `POST /auth/password/reset`, which revoke every
  session for the account.
* `POST /api/v1/auth/logout` revokes only the current session; `POST /api/v1/auth/logout-all`
  revokes every session for that account.
* Passwords are hashed with **Argon2id**. Opaque tokens (verification / reset) are stored
  only as SHA-256 hashes.
* `POST /api/v1/auth/verify-email/request` and `/password/forgot` never reveal whether an
  address exists. In development (`DEV_MODE_ENABLE_TOKEN_LINKS=true`) the response also
  carries `dev_link` and `dev_token` so the flow is testable without SMTP.
* `POST /api/v1/auth/dev/promote` grants the caller `admin`, but only when
  `DEBUG=true` **and** `APP_ENV` is not `production`; otherwise it returns `404`.

### Roles

| Role | Access |
|---|---|
| `user` | Everything scoped to their own rows |
| `admin` | Everything a `user` gets **plus** the entire `/api/v1/admin/*` surface |

Authorization is enforced per row: another user's resource always looks like a `404`,
never a `403`, so ids cannot be enumerated.

---

## 2. Error envelope

Every non-2xx response uses the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [{ "field": "email", "message": "value is not a valid email address", "type": "value_error" }],
    "request_id": "8f1c0a2b7d3e4f50"
  }
}
```

`details` is a list for field-level validation errors, an object for structured context,
and is omitted when there is nothing to add. `request_id` matches the `X-Request-ID`
response header (a client-supplied value is echoed back).

| Status | Typical `code` |
|---|---|
| 401 | `unauthorized`, `token_invalid`, `token_expired`, `session_revoked`, `invalid_credentials`, `refresh_invalid` |
| 403 | `forbidden`, `account_inactive` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `conflict`, `email_taken`, `duplicate_email`, `duplicate` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `validation_error`, `token_invalid`, `invalid_password`, `duplicate_email` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 502 | `ai_provider_error`, `ai_response_invalid` |

---

## 3. Pagination

List endpoints that return collections use:

```json
{
  "items": [ ... ],
  "total": 57,
  "page": 1,
  "page_size": 20,
  "pages": 3,
  "has_next": true,
  "has_previous": false
}
```

`page` starts at 1. `page_size` defaults to 20 and is capped at 100 for listings
(1000 for the CSV export).

---

## 4. Rate limiting

In-memory sliding window, keyed by `bucket:client-ip`. Disabled with
`RATE_LIMIT_ENABLED=false`.

| Bucket | Limit |
|---|---|
| `auth:signup` | 5 / minute |
| `auth:login` | 10 / minute |
| `auth:refresh`, `auth:sensitive`, email writes, imports, assistant | 20 / minute |

Exceeding a bucket returns `429` with `details.retry_after_seconds`.

---

## 5. Endpoint reference

### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness. No database access. |
| GET | `/health/ready` | Readiness; returns `503` when the DB is unreachable. |

### Auth, profile, preferences

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/signup` | `201` + token pair. Password must be ≥ 8 chars. |
| POST | `/auth/login` | Updates `last_login_at`. |
| POST | `/auth/refresh` | Body `{ "refresh_token": "..." }`; rotates the pair. |
| POST | `/auth/logout` | Revokes the supplied refresh token and the access token bound to it. |
| POST | `/auth/logout-all` | Revokes every session for the caller. |
| POST | `/auth/verify-email/request` | `{ "email": "..." }` |
| POST | `/auth/verify-email/confirm` | `{ "token": "..." }` |
| POST | `/auth/password/forgot` | `{ "email": "..." }` |
| POST | `/auth/password/reset` | `{ "token": "...", "new_password": "..." }` |
| POST | `/auth/password/change` | Requires the current password; signs out all sessions. |
| GET/PATCH | `/auth/me` | Profile. `timezone` here and in preferences are the same value. |
| GET/PUT | `/auth/me/preferences` | `default_reply_tone`, `digest_enabled`, `timezone`, `notification_channels`. |
| POST | `/auth/dev/promote` | Development only. |

### Inbox

| Method | Path | Notes |
|---|---|---|
| POST | `/emails` | Manual creation. `process_with_ai` (default `true`) runs analysis inline. |
| GET | `/emails` | Filterable, sortable, paginated listing (see §6). |
| GET | `/emails/export.csv` | CSV export honouring `q` and `category`; values are formula-injection safe. |
| GET | `/emails/{id}` | Detail incl. `analysis` and `extracted[]`. |
| PATCH | `/emails/{id}` | Edit `subject` / `from_name` / `body_text` (preview regenerated). |
| DELETE | `/emails/{id}` | **Soft delete** – sets `is_deleted`/`deleted_at`. |
| POST | `/emails/{id}/restore` | Undoes a soft delete. |
| POST | `/emails/{id}/state` | `{ is_read?, is_starred?, is_archived? }` – at least one required. |
| POST | `/emails/{id}/process` | Runs or retries AI analysis; returns `502` if the provider fails. |
| POST | `/emails/import/eml` | `multipart/form-data`, field `files` (repeatable), `.eml` only. |
| POST | `/emails/import/dataset` | `multipart/form-data`, field `file`; optional form field `process_with_ai`. |

Import responses use `ImportSummary`:

```json
{ "source": "csv", "filename": "inbox.csv", "received": 63, "created": 63,
  "duplicates": 0, "failed": 0, "errors": [], "email_ids": [1, 2, 3] }
```

Rows are validated individually: a bad row increments `failed` and appends to `errors`
instead of aborting the batch.

**Threads** – `GET /threads` and `GET /threads/{id}` group messages by `thread_key`,
derived from `In-Reply-To`/`Message-ID` or the `RE:`/`FWD:`-stripped subject.

### Smart replies

| Method | Path | Notes |
|---|---|---|
| GET | `/replies` | Filters: `email_id`, `status` (`draft`/`approved`/`rejected`). |
| POST | `/replies/email/{id}` | `{ tone, regenerate, instructions }`. Re-requesting the same tone reuses the existing draft unless `regenerate=true`. |
| GET | `/replies/{id}` | Draft detail. |
| PATCH | `/replies/{id}` | Edit `body` (sets `is_edited`, keeps `original_body`), change `tone`, set `status`. |
| DELETE | `/replies/{id}` | Discard the draft. |

Nothing is ever transmitted to a recipient – drafts are stored state only.

### Action items and deadlines

| Method | Path | Notes |
|---|---|---|
| GET | `/actions` | Filters: `status` (comma-separated), `email_id`, `overdue`. |
| PATCH | `/actions/{id}` | Update `status`, `description`, `owner`, `due_date`, `due_text`. |
| POST | `/actions/{id}/complete` | Idempotent completion stamp. |
| DELETE | `/actions/{id}` | Dismiss (`status=dismissed`). |
| GET | `/actions/deadlines` · `/actions/deadlines/upcoming` | `horizon_days` (0–365, default 14). Days ≤ 1 also raise a `deadline_upcoming` notification. |

### Notifications

| Method | Path | Notes |
|---|---|---|
| GET | `/notifications` | `unread_only`, `type` (validated against `NotificationType`). |
| GET | `/notifications/unread-count` | `{ "unread": n }` |
| POST | `/notifications/read-all` | Optional `{ "ids": [...] }`; otherwise all. |
| POST | `/notifications/{id}/read` | Optional `{ "is_read": true }`. |
| DELETE | `/notifications/{id}` | Dismiss. |
| GET/PUT | `/notifications/preferences/me` | `in_app_enabled`, `daily_digest`, `enabled_types`. |

Notification types: `urgent_email`, `customer_complaint`, `reply_required`,
`deadline_upcoming`, `action_item`, `ai_processing_completed`,
`ai_processing_failed`. Types disabled by default are suppressed at creation time
(`ai_processing_completed` is off by default).

### Inbox assistant

| Method | Path | Notes |
|---|---|---|
| POST | `/assistant/query` | One-off question, no conversation row. |
| GET/POST | `/assistant/conversations` | List / start a conversation. |
| GET/DELETE | `/assistant/conversations/{id}` | Detail (with messages) / delete. |
| POST | `/assistant/conversations/{id}/messages` | Ask inside a conversation; increments `message_count` by 2. |

Answer shape (`AssistantAnswer`):

```json
{
  "conversation_id": null,
  "message": { "id": 0, "role": "assistant", "content": "...", "filters": {...},
               "citations": [12, 7], "created_at": "..." },
  "applied_filters": { "reply_required": true, "urgency": "high" },
  "total_matches": 3,
  "results": [{ "id": 12, "subject": "...", "sender": "...", "category": "urgent",
                "priority": "high", "sentiment": "urgent", "reply_required": true,
                "summary": "...", "is_read": false }],
  "answer": "I found 3 matching email(s) ... References: [#12], [#7].",
  "deterministic": false
}
```

`applied_filters` contains only **allow-listed, backend-validated** filters – the model
never supplies SQL. `citations` always reference ids present in `results`.

### Dashboard and analytics

| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/summary` | Counters + distributions + recent emails/activity in one call. |
| GET | `/dashboard/counters` | `total_emails`, `unread_emails`, `urgent_emails`, `reply_required`, `action_required`, per-category counters, `pending_actions`, `overdue_actions`, `unread_threads`, `processed_emails`, `failed_emails`, `pending_processing`. |
| GET | `/dashboard/activity` | `days` (1–365, default 30) → `[{ date, received, read, replied, urgent }]`. |
| GET | `/dashboard/categories` · `/sentiments` · `/priorities` | Distribution rows with `percentage`. |
| GET | `/dashboard/recent-emails` | `limit` (1–50). |
| GET | `/dashboard/recent-activity` | `limit` (1–50) – AI processing events. |
| GET | `/dashboard/deadlines` | Upcoming and overdue deadlines. |
| GET | `/analytics` | `date_from` / `date_to` (ISO dates, default: last 30 days) → full report incl. `avg_response_time_seconds` (null when the sample is unreliable). |

### Admin (`role=admin` required)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/stats` | Global counters incl. `ai_calls_total`, `ai_calls_failed`, `ai_tokens_total`, `ai_errors_last_24h`. |
| GET | `/admin/users` | `q`, `role`, `active`, pagination; each row carries `email_count`. |
| PATCH | `/admin/users/{id}` | Change `role` / `is_active` / `is_verified`. You cannot demote or deactivate yourself. |
| GET | `/admin/ai/usage` | `purpose` (`analysis`/`reply`/`assistant`), `limit`. |
| GET | `/admin/ai/errors` | `error_code`, `limit`. |
| GET | `/admin/audit-logs` | `action`, `limit`. |
| GET/POST | `/admin/categories` | Catalogue; seeded from the canonical list on first read. |
| PATCH | `/admin/categories/{id}` | `label`, `description`, `is_active`, `sort_order`. |
| GET | `/admin/config` | System configuration rows. |
| PUT | `/admin/config/{key}` | `{ value, description }`; creates or updates, records `updated_by`. |

---

## 6. Email filters

Query parameters on `GET /api/v1/emails` (all optional, all composable):

| Parameter | Type | Notes |
|---|---|---|
| `q` | string | Case-insensitive match over subject, body, from name/address, preview. |
| `subject`, `from_address` | string | Substring match. |
| `category`, `priority`, `sentiment` | csv list | Validated against the canonical enums; invalid values → `422`. |
| `date_from`, `date_to` | `YYYY-MM-DD` | Inclusive on both ends; `from > to` → `422`. |
| `unread`, `starred`, `archived`, `deleted` | bool | See the default-exclusion rules below. |
| `urgent` | bool | `priority IN (high, critical) OR sentiment = 'urgent'`. |
| `reply_required`, `action_required` | bool | Straight from the analysis row. |
| `direction` | `inbound` / `outbound` | |
| `processing_status` | `pending`/`processing`/`completed`/`failed`/`skipped` | |
| `customer`, `order_number` | string | Match against extracted entities (`customer_name`/`company`, `order_number`/`invoice_number`). |
| `has_attachments` | bool | |
| `thread_id` | int | |
| `sort_by` | `received_at` (default), `created_at`, `subject`, `priority`, `size_bytes` | |
| `sort_order` | `asc` / `desc` (default `desc`) | |
| `page`, `page_size` | int | `page ≥ 1`, `1 ≤ page_size ≤ 100`. |

**Default exclusions:** when `archived` and `deleted` are omitted, both are excluded, so
the plain listing is "active inbox only". Pass `archived=true` or `deleted=true`
explicitly to include them.

---

## 7. AI layer

* Provider is selected by `AI_PROVIDER` (`mock` | `gemini`). With `AI_PROVIDER=gemini`
  and an empty `AI_API_KEY` the factory logs a warning and falls back to `mock`, so the
  app always starts.
* Every call is schema-validated (`EmailAnalysisModel`, `ReplyModel`) before it touches
  the database. Invalid output → `502 ai_response_invalid`, **never** a partial write.
* Every call writes an `ai_usage_records` row; failures additionally write an
  `ai_error_logs` row and mark the email `processing_status=failed` with
  `processing_error=<error code>`.
* Email content is fenced inside `<email_content>…</email_content>` with an explicit
  injection guard in the system prompt; the model is told that block is untrusted data.
* Prompt versions (`ANALYSIS_PROMPT_VERSION`, `REPLY_PROMPT_VERSION`) and schema versions
  are persisted on each analysis so re-processing is traceable.

### Analysis output

`EmailDetail.analysis` carries `category`, `intent`, `priority` + `priority_reason`,
`sentiment`, `reply_required`, `action_required`, `summary_short`, `summary_detailed`,
`key_points[]`, `unresolved_issues[]`, `provider`, `model`, `prompt_version`,
`schema_version`, `latency_ms`, `analyzed_at`.

`EmailDetail.extracted[]` carries `field`, `value_text`, `value_normalized`,
`raw_phrase`, `confidence`, `evidence` for `customer_name`, `company`, `phone`,
`email`, `order_number`, `invoice_number`, `product`, `amount`, `currency`, `date`,
`deadline`, `meeting_date`, `location`, `requested_action`.

### Domain rules

* **Urgent** means `priority ∈ {high, critical}` **or** `sentiment = urgent`. This single
  definition is used by the `urgent=true` filter, the `urgent_emails` counter and the
  `urgent_email` notification.
* `category`, `priority` and `sentiment` live **only** on `email_analysis`; list and
  detail responses join them rather than duplicating them onto `emails`.
* `users.timezone` and `user_preferences.timezone` are kept in sync in both directions.
* `POST /emails` rejects an identical message for the same user with
  `422 duplicate_email` (SHA-256 fingerprint over user + sender + subject + timestamp +
  body prefix).
* All timestamps are stored and returned as UTC (`…Z`).

---

## 8. Quick start

```bash
# 1. register + sign in
curl -X POST localhost:8000/api/v1/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"Sup3rSecret!1","full_name":"Me"}'

# 2. create an email (analysis runs inline)
curl -X POST localhost:8000/api/v1/emails \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"subject":"URGENT: server down","from_address":"ops@acme.test",
       "body_text":"Production is down, please respond ASAP. Order ORD-1."}'

# 3. find what needs a reply
curl 'localhost:8000/api/v1/emails?urgent=true&reply_required=true' -H "Authorization: Bearer $ACCESS"

# 4. draft a reply (nothing is ever sent)
curl -X POST localhost:8000/api/v1/replies/email/1 \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"tone":"friendly"}'

# 5. ask the assistant
curl -X POST localhost:8000/api/v1/assistant/query \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"query":"Which emails need my reply today?"}'
```
