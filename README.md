# AtlasLM

AtlasLM is a self hosted research workspace for asking questions over your own documents. Upload PDFs, markdown, or text, then ask questions and get answers with source citations.

I built this because AI answers are much more useful when you can see where they came from. The goal is not just chat over documents, but answers that point back to the right file, page, and source text.

## What it does

- Upload PDFs, markdown files, plain text, or crawled pages
- Split documents into chunks with page and source metadata
- Store embeddings in PostgreSQL with pgvector
- Ask questions through a chat UI
- Stream answers from the backend
- Show citation badges that open the related source text
- Support multiple model providers, including local Ollama setups
- Keep provider keys on the server

## Tech stack

- Next.js frontend
- FastAPI backend
- PostgreSQL with pgvector
- Redis for jobs and cache
- Docker Compose and Nginx
- Supabase auth
- PyMuPDF for PDF parsing

## Screenshots

![Workspace dashboard](screenshots/dashboard.png)

![Landing page](screenshots/landing_hero.png)

| Mobile view | Pricing view |
| --- | --- |
| ![Mobile](screenshots/landing_hero_mobile.png) | ![Pricing](screenshots/pricing.png) |

## Run it with Docker

```bash
git clone https://github.com/janpaul80/AtlasLM.git
cd AtlasLM
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
docker-compose up --build -d
```

Then open:

- Web app: `http://localhost:3010`
- API docs: `http://localhost:8080/docs`

## Local development

Backend:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Notes

- `frontend/` has the web app.
- `backend/` has ingestion, chat, provider calls, and citation logic.
- `migrations/` has database setup.
- `screenshots/` has product images used in this README.
- `docker-compose.yaml` runs the app stack locally.

## Status

Active prototype. The core idea is working, but a production install still needs careful setup for auth, storage, provider keys, backups, and rate limits.
