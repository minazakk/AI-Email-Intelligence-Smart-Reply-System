# AI Email Intelligence & Smart Reply System

Full-stack AI-powered email management platform with smart replies, inbox assistant, and analytics.

## Tech Stack

- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS, Radix UI, Recharts
- **Backend:** FastAPI, SQLAlchemy 2, PostgreSQL, Alembic
- **AI:** Gemini/OpenAI provider adapter with mock fallback
- **Background Tasks:** Celery + Redis
- **Auth:** JWT with rotating refresh tokens, Argon2id hashing

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- PostgreSQL 14+
- Redis

### 1. Clone & Setup Backend

```bash
cd AI-Email-Intelligence-Smart-Reply-System

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
alembic upgrade head

# Seed demo data (optional)
python scripts/seed_demo.py

# Start backend
uvicorn app.main:app --reload --port 8000
```

### 2. Setup Frontend

```bash
# Install dependencies
npm install

# Setup environment
cp .env.example .env.local
# Update NEXT_PUBLIC_API_URL if needed

# Start frontend
npm run dev
```

### 3. Access

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

**Demo credentials:** `demo@example.com` / `DemoPassw0rd!`

## Project Structure

```
├── app/                    # FastAPI backend
│   ├── api/v1/            # Route handlers
│   ├── core/              # Config, security, errors
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   └── services/          # Business logic + AI
├── src/                    # Next.js frontend
│   ├── app/               # Pages (App Router)
│   ├── components/        # Shared components
│   ├── hooks/             # Custom hooks (auth)
│   ├── lib/               # API client
│   └── types/             # TypeScript types
├── Pipeline/               # Celery background tasks
├── alembic/               # Database migrations
├── tests/                 # Pytest test suite
└── data/                  # Seed data
```

## Deployment

### Frontend (Vercel)

1. Import repo on [vercel.com](https://vercel.com)
2. Set env var: `NEXT_PUBLIC_API_URL=https://your-backend.com/api/v1`
3. Deploy

### Backend (Railway/Render)

1. Create PostgreSQL database
2. Create Redis instance
3. Deploy with Dockerfile
4. Set environment variables from `.env.example`
5. Run migrations: `alembic upgrade head`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/signup` | Create account |
| `POST /api/v1/auth/login` | Login |
| `GET /api/v1/emails` | List emails |
| `POST /api/v1/emails` | Create email |
| `GET /api/v1/emails/{id}` | Email detail |
| `POST /api/v1/replies/email/{id}` | Generate smart reply |
| `GET /api/v1/dashboard/summary` | Dashboard stats |
| `POST /api/v1/assistant/query` | AI assistant |

## License

MIT