# AI Email Intelligence & Smart Reply System

## 1. Project overview

The **AI Email Intelligence & Smart Reply System** is an AI-powered
email management platform for business workflows. It is designed to
reduce the manual effort required to read, organize, prioritize,
understand, and respond to business emails.

The system should process real email content supplied by the user,
classify and summarize it, extract useful details, identify urgency and
required actions, suggest context-aware replies, answer questions about
the user's inbox, and present activity through a dashboard and analytics
views.

This is an internship-grade engineering project, not a basic chatbot or
a simple email summarizer. The system must use actual stored email data,
reliable APIs, validated AI outputs, user-scoped access controls, and
repeatable tests.

## 2. Project goals

-   Understand incoming business emails and conversation threads.
-   Automatically classify emails by their main purpose and intent.
-   Generate short and detailed summaries.
-   Extract customer, company, order, invoice, amount, date, deadline,
    meeting, location, and requested-action details where present.
-   Detect sentiment, priority, urgency, reply requirements, and action
    requirements.
-   Identify action items and normalize deadlines when the available
    context supports it.
-   Generate editable, tone-aware smart reply drafts using the full
    thread context.
-   Answer inbox questions and support natural-language email search
    using the user's actual email data.
-   Provide dashboard metrics, charts, notifications, and analytics.
-   Protect account data, AI credentials, email content, and access
    boundaries.

## 3. Recommended technology

  -----------------------------------------------------------------------
  Area                                Recommended technology
  ----------------------------------- -----------------------------------
  Frontend                            React or Next.js with TypeScript

  Backend API                         Python + FastAPI

  Database                            PostgreSQL

  ORM / migrations                    SQLAlchemy 2.x and Alembic, if
                                      compatible with the existing
                                      repository

  Validation                          Pydantic

  AI provider                         Gemini, OpenAI, or Claude through a
                                      server-side provider adapter

  Background processing               Redis + Celery or an equivalent
                                      queue, if needed by the repository

  Testing                             pytest and deterministic
                                      mocked-provider tests

  API documentation                   FastAPI OpenAPI / Swagger UI

  Configuration                       Environment variables and a
                                      committed `.env.example` containing
                                      placeholders only
  -----------------------------------------------------------------------

Use the technology already established in the repository where
practical. Avoid introducing infrastructure that is not needed for a
working core system.

## 4. Main user-facing modules

### 4.1 Authentication and profile

-   Sign up, login, logout.
-   Forgot password and reset password.
-   Email verification.
-   User profile and preferences.
-   Role-based access, including user and admin.
-   Strict separation of each user's emails, analysis, replies, actions,
    notifications, and assistant history.

### 4.2 Dashboard

Display real, user-scoped metrics: - Total emails. - Unread emails. -
Urgent emails. - Emails requiring replies. - Customer, sales, and
support emails. - Pending actions and upcoming deadlines. - Email
activity chart. - Category distribution. - Sentiment trends. - Recent
emails and recent AI processing activity.

### 4.3 Inbox and email management

Each email should show: - Sender, subject, short preview, date/time. -
Read/unread state. - Category, priority, and AI processing status.

Users should be able to: - Open email details. - Mark read/unread. -
Star/unstar. - Archive/unarchive. - Delete/restore according to the
chosen retention model. - Search and combine filters. - View full email
threads with expandable previous messages.

### 4.4 Email input and import

The initial internship version must not require Gmail or Outlook
integration. Support: - Manual email creation or pasted email text. -
`.eml` upload. - CSV and JSON dataset import. - A reproducible synthetic
test dataset. - Input validation, file size limits, safe parsing,
duplicate handling, and useful import errors.

Gmail/Outlook integration can be added later as a separate, explicitly
scoped enhancement.

### 4.5 Email categories

Recommended machine-readable categories: - `sales_inquiry` -
`customer_complaint` - `support_request` - `meeting_request` -
`invoice_payment` - `job_application` - `general_information` - `spam` -
`urgent` - `other`

Category describes the primary purpose of an email. Priority/urgency
must be represented separately. If the email is both a complaint and
urgent, preserve the complaint category and set a suitable priority
unless the established API contract specifically requires another
representation.

### 4.6 AI analysis

For each processed email, determine: - Category. - Intent. - Priority
and a short evidence-based reason. - Sentiment and confidence where
supported. - Whether a reply is required. - Whether an action is
required. - Short summary and detailed summary. - Extracted
information. - Action items and deadlines. - Key points and unresolved
issues. - Processing status and provider/model metadata where
appropriate.

Never invent details missing from the email. Use `null`, empty lists, or
an explicit `other` value when information is unknown. Preserve the
original email separately from generated analysis.

### 4.7 Priority and sentiment

Priority levels: - `low` - `medium` - `high` - `critical`

Sentiment values: - `positive` - `neutral` - `negative` - `angry` -
`urgent`

Sentiment and urgency are different. An email can be urgent without
being angry or negative. Explain priority using concise evidence from
the message rather than unsupported assumptions.

### 4.8 Information extraction

Extract available details such as: - Customer name and company. - Phone
number and email address. - Order and invoice number. - Product and
amount/currency. - Dates, deadlines, and meeting date. - Location. -
Requested action.

Keep original date phrases as well as normalized dates when possible.
Use the email timestamp and configured timezone as the reference for
relative dates. If a deadline is ambiguous, preserve the raw phrase and
leave the normalized date empty rather than guessing.

### 4.9 Action items and deadlines

Detect tasks such as "send the updated quotation by Friday." Each action
item should support: - Description. - Owner when explicitly known. -
Original deadline text. - Normalized due date where possible. - Status
(`pending`, `in_progress`, `completed`, `dismissed`). - Source email. -
Completion timestamp where applicable.

Users must be able to mark actions completed. Upcoming deadlines should
be visible on the dashboard.

### 4.10 Smart Reply

The email detail view should allow users to: - Generate a reply. -
Regenerate a draft. - Select tone. - Edit and copy the reply. - Approve
or reject the suggestion.

Supported tones: - `professional` - `friendly` - `short` - `detailed` -
`apologetic` - `formal`

Smart replies must use the complete thread context, respond to the
latest message, avoid repeating already answered questions, and avoid
unsupported claims or commitments. The AI must **never send an email
automatically**. The user must remain in control of any reply.

### 4.11 AI inbox assistant and intelligent search

Example queries: - "Which emails need my reply?" - "Show all urgent
customer complaints." - "What are today's pending actions?" - "Which
emails mention payment?" - "Summarize today's important emails." -
"Which customers are waiting for a response?" - "Find payment-related
emails from this week." - "Find all angry customers."

Use authenticated, user-scoped email records. Use deterministic database
queries for exact counts and filters. Natural-language interpretation
may produce a validated filter object, but backend authorization and
query execution must remain in control. Do not fabricate emails or
results.

### 4.12 Search and filters

Support searches across: - Sender. - Subject and body keywords. -
Category and priority. - Date range. - Sentiment. - Customer and order
number. - Read/unread state. - Urgent. - Reply required. - Action
required.

Filters should be combinable.

### 4.13 Notifications

Support notifications for: - New urgent email. - Customer complaint. -
Email requiring a reply. - Upcoming deadline. - Important action item. -
AI processing completed.

Users should be able to configure notification preferences.

### 4.14 Analytics

Display user-scoped analytics for: - Emails received and replied to. -
Average response time where reliable source data exists. - Urgent
emails. - Customer complaints. - Sales inquiries. - Support requests. -
Emails by category. - Sentiment trends. - Pending actions.

Do not hardcode analytics or show mock figures as real data.

### 4.15 Admin panel

Admin capabilities may include: - User management. - Email processing
status. - AI usage statistics. - Category and system settings. - AI logs
and processing errors. - System activity and audit logs.

Admin-only operations must be protected by server-side authorization.

## 5. AI processing architecture

``` text
Email Input (manual / .eml / CSV / JSON)
        |
        v
Email Parser and Validation
        |
        v
Text Cleaning and Metadata Normalization
        |
        v
AI Classification and Intent Detection
        |
        v
Summary Generation
        |
        v
Information Extraction
        |
        v
Sentiment and Priority Detection
        |
        v
Action Item and Deadline Detection
        |
        v
Schema Validation and Normalization
        |
        v
Database Persistence and Processing Status
        |
        +------> Inbox, Filters, Analytics
        |
        +------> Smart Reply using thread context
        |
        +------> Inbox Assistant / RAG / Natural-language Search
```

Provider calls should be behind a service interface. Use bounded
timeouts, limited retries, useful processing errors, and validated
structured output. A mocked provider must make tests runnable without
API credentials.

## 6. Suggested database entities

The implementation should use appropriate relationships, constraints,
and indexes for: - Users and preferences. - Email threads. - Emails. -
Sender/recipient metadata. - Categories or category configuration. - AI
analysis. - Extracted information. - Action items. - Deadlines. -
Suggested replies and reply history/status. - Notifications and
notification preferences. - AI assistant conversations and messages. -
Audit logs. - AI usage, processing status, and error records. -
Admin/system configuration where needed.

Use the repository's existing ORM patterns. Keep original email content
separate from AI-derived content and avoid unnecessary duplicated data.

## 7. Security, privacy, and reliability requirements

-   Secure password hashing and expiring, single-use verification/reset
    tokens.
-   Authentication, authorization, role checks, and object-level
    ownership checks.
-   Strict per-user data isolation across emails, threads, analysis,
    replies, actions, notifications, analytics, and assistant
    conversations.
-   Validate request bodies, imports, dates, filters, and model outputs.
-   Protect against oversized or malformed uploads and unsafe `.eml`
    parsing.
-   Use parameterized database access; never execute model-generated
    SQL.
-   Treat email bodies and imported content as untrusted data, including
    prompt-injection attempts.
-   Keep AI keys and other secrets server-side in environment variables.
-   Do not log passwords, tokens, API keys, or full email bodies by
    default.
-   Use safe public errors and structured internal logs.
-   Configure CORS and rate limiting deliberately.
-   Use soft deletion/retention rules consistently.
-   Never automatically send AI-generated replies.
-   Do not represent an AI/provider failure as a successful analysis.
-   Do not claim production readiness without the relevant verification.

## 8. Recommended API areas

Exact paths should follow the implemented API contract, but the API
should cover: - Authentication and profile. - Email creation, import,
listing, details, and state changes. - Threads and thread context. - AI
processing, classification, summarization, and extraction. - Smart reply
generation and draft status. - Search and combined filters. - Action
items and deadlines. - Inbox assistant conversations and Q&A. -
Notifications and preferences. - Dashboard and analytics. - Admin users,
configuration, AI usage, processing logs, and errors. - Health/readiness
checks.

Document auth requirements, request/response schemas, enums, pagination,
error format, and AI service integration in `docs/API_CONTRACT.md`.

## 9. Standard synthetic test dataset

Create at least 50--100 synthetic emails. Aim for at least 10 examples
in each of these groups: - Customer complaints. - Sales inquiries. -
Support requests. - Meeting requests. - Payment/invoice emails. - Job
applications. - General emails. - Urgent emails. - Spam/unwanted emails.

Categories may overlap. Use synthetic identities and data; do not
include real personal information. Include expected outcomes for
representative cases and an evaluation/test report. Measure performance
through the included evaluation process rather than inventing accuracy
claims.

## 10. Testing and acceptance criteria

### Backend and database

-   Authentication and password handling work.
-   User/admin authorization is enforced.
-   Cross-user data access is blocked.
-   Email CRUD, thread retrieval, import validation, and state changes
    work.
-   Search and combined filters work with pagination and date ranges.
-   Actions, deadlines, notifications, and reply drafts persist
    correctly.
-   Analytics use real, user-scoped records.
-   Migrations and OpenAPI schema can be generated.
-   Safe error handling and input validation are tested.

### AI logic

-   Structured outputs are schema-validated.
-   Missing information is not fabricated.
-   Categories, priority, and sentiment are distinct and consistent.
-   Short and detailed summaries are useful and grounded in the email.
-   Extracted information and action items include evidence where
    appropriate.
-   Relative dates are normalized correctly when context is sufficient.
-   Thread-aware replies respect the selected tone and do not make
    unsupported commitments.
-   Inbox Q&A only uses retrieved records belonging to the authenticated
    user.
-   Provider errors, malformed JSON, timeouts, and rate limits are
    handled.
-   Prompt-injection content in email bodies does not override system
    instructions.
-   No email is sent automatically.

### End-to-end application

-   Frontend and backend use matching API schemas.
-   Dashboard charts display real data.
-   Loading, empty, error, and processing states are represented.
-   The setup instructions can be followed on a clean development
    environment.
-   Tests run without a live AI key where possible by using a mocked
    provider.
-   Known limitations and external setup requirements are documented
    honestly.

## 11. Local setup and configuration

The exact commands depend on the repository's implementation. At
minimum, document: 1. Supported Python and Node versions. 2. How to
create and activate a Python virtual environment. 3. How to install
backend dependencies. 4. How to install frontend dependencies, if a
frontend exists. 5. How to configure PostgreSQL and create a development
database. 6. How to copy `.env.example` to `.env` and fill in local
values. 7. How to run database migrations. 8. How to start the backend
and frontend. 9. How to run tests and lint/type checks. 10. How to
import the synthetic dataset and verify the demo. 11. Where to find
OpenAPI docs and health endpoints. 12. Which features require external
credentials.

Never commit `.env`, production credentials, real customer emails, or
API keys.

## 12. Environment variable guidance

Keep `.env.example` limited to variable names and safe placeholders.
Expected settings may include: - Application environment and secret
key. - Database URL. - CORS allowed origins. - Authentication/token
settings. - AI provider and model. - AI API key. - Provider
timeout/retry settings. - Optional Redis/worker settings. - Email
delivery configuration for verification/reset, if enabled. - Upload size
and allowed import settings.

The exact names must match the implementation. Do not invent that a
service is configured when it is not.

## 13. Deliverables

-   Complete source code.
-   Responsive web application, if included in the repository scope.
-   Secure authentication and user isolation.
-   Email inbox, details, threads, and import.
-   AI classification and summaries.
-   Sentiment, priority, information extraction, actions, and deadlines.
-   Context-aware smart reply drafts with tone selection and approval
    controls.
-   Inbox AI assistant and intelligent search.
-   Search, combined filters, notifications, and analytics.
-   Backend REST APIs and database migrations.
-   Admin tools and audit/processing logs.
-   Synthetic 50--100+ email test dataset and expected-result fixtures.
-   Automated tests and an honest test report.
-   API contract and OpenAPI documentation.
-   `.env.example`, setup instructions, and this README.
-   Deployment instructions and demo walkthrough/video plan.

## 14. Definition of done

The project is not complete merely because the UI loads or an LLM
returns text. A feature is complete when it is integrated with real
stored email data, validates inputs and outputs, respects user
authorization, has useful error handling, is covered by appropriate
tests, and is documented. Any unverified external integration or known
limitation must be explicitly listed in the handoff.
