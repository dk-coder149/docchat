# DocChat

Upload PDF / TXT documents and chat with them. Answers are generated from **your** documents (RAG) and stream in word by word, with the source files shown under each answer.

**Stack:** FastAPI · PostgreSQL · ChromaDB · LLM API (Groq by default; Claude or any OpenAI-compatible provider is a one-line switch) · plain HTML/CSS/JS (served by nginx) · Docker Compose

## How the three parts connect

```
 Browser
    │  opens http://localhost:3000
    ▼
┌──────────────┐   fetch() to API_BASE_URL    ┌────────────────────┐
│  FRONTEND    │ ───────────────────────────► │  BACKEND (FastAPI) │
│  nginx :3000 │ ◄─── JSON / NDJSON stream ── │  :8000             │
└──────────────┘      (CORS must allow it)    └───┬──────┬──────┬──┘
                                                  │      │      │
                              DATABASE_URL        │      │      │  GROQ_API_KEY
                     ┌────────────────────────────┘      │      └──────────────┐
                     ▼                                   ▼                     ▼
              ┌─────────────┐                     ┌─────────────┐        ┌─────────────┐
              │ PostgreSQL  │                     │  ChromaDB   │        │ Claude API  │
              │ users, docs │                     │ text chunks │        │ writes the  │
              │ chat history│                     │ + embeddings│        │ answer      │
              └─────────────┘                     └─────────────┘        └─────────────┘
                                                  CHROMA_PATH (a volume)
```

| Connection | How it is wired | Setting |
|---|---|---|
| Frontend → Backend | Browser JavaScript calls the backend URL | `API_BASE_URL` (frontend) |
| Backend allows Frontend | CORS allow-list | `CORS_ORIGINS` (backend) — must equal the address in the browser bar |
| Backend → PostgreSQL | SQLAlchemy connection string | `DATABASE_URL` (in Docker the host is `db`) |
| Backend → ChromaDB | Local folder, kept in a Docker volume | `CHROMA_PATH` |
| Backend → LLM | Provider + API key | `LLM_PROVIDER` and `GROQ_API_KEY` (see [Choosing the AI model](#choosing-the-ai-model)) |

If the chat says *"Cannot reach the server"* or the browser console shows a **CORS error**, these two values do not match: `API_BASE_URL` and `CORS_ORIGINS`.

## Folder structure

```
docchat/
├── docker-compose.yml        # starts db + backend + frontend together
├── .env.example              # copy to .env and fill in
├── .gitignore
├── README.md
│
├── backend/                  # FastAPI API
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py           # app, CORS, middleware, routers, /health
│   │   ├── config.py         # settings from environment / .env
│   │   ├── database.py       # SQLAlchemy engine + session
│   │   ├── models.py         # tables: User, Document, ChatMessage
│   │   ├── schemas.py        # Pydantic request/response shapes
│   │   ├── security.py       # password hashing + JWT
│   │   ├── deps.py           # get_current_user (Depends)
│   │   ├── limiter.py        # rate limiting
│   │   ├── textproc.py       # PDF/TXT text extraction + chunking
│   │   ├── rag.py            # ChromaDB: store / search / delete chunks
│   │   ├── llm.py            # LLM streaming (Groq / Claude / OpenAI-compatible) + prompt
│   │   └── routers/
│   │       ├── auth.py       # signup, login, me
│   │       ├── documents.py  # upload (background task), list, delete
│   │       └── chat.py       # streaming RAG chat, history
│   └── tests/
│
└── frontend/                 # static site, no build step
    ├── Dockerfile / nginx.conf
    ├── docker-entrypoint.d/  # writes js/config.js from API_BASE_URL at start
    ├── index.html
    ├── css/style.css
    ├── js/
    │   ├── config.js         # API_BASE_URL
    │   ├── api.js            # every fetch() call to the backend
    │   └── app.js            # UI logic
    └── tests/api.test.js
```

## Run with Docker (recommended)

Needs Docker Desktop (or Docker Engine + Compose).

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, POSTGRES_PASSWORD, GROQ_API_KEY
docker compose up --build
```

Open **http://localhost:3000**, sign up, upload a PDF, wait for the status to say `ready`, and ask a question.
API docs (Swagger): http://localhost:8000/docs

Stop: `Ctrl+C`, or `docker compose down` (add `-v` to also delete the database and uploaded documents).

## Run without Docker (development)

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

# from the project root: cp .env.example .env  and set SECRET_KEY + GROQ_API_KEY
# (without DATABASE_URL it uses a local SQLite file, no PostgreSQL needed)
uvicorn app.main:app --reload --port 8000
```

**Frontend** (any static server):

```bash
cd frontend
python -m http.server 3000
```

Open http://localhost:3000. `frontend/js/config.js` already points to `http://localhost:8000`.

## Choosing the AI model

Only `backend/app/llm.py` talks to the AI provider; everything else stays the same. Pick one in `.env`:

| `LLM_PROVIDER` | Needs | Notes |
|---|---|---|
| `groq` (default) | `GROQ_API_KEY` | Default model `openai/gpt-oss-20b`. Change with `LLM_MODEL`. Free-plan limits are per organization and shared by all your keys, so check your own limits page in the Groq console. |
| `anthropic` | `ANTHROPIC_API_KEY` | Claude (paid API). Default model `claude-sonnet-5-5`. |
| `openai_compatible` | `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` if the server wants one | Ollama (local, no key), Gemini, OpenRouter, Cerebras… see the examples in `.env.example`. |

To save free-quota tokens, the app sends only the last 4 chat messages (`HISTORY_MESSAGES`) and the 4 best-matching chunks (`TOP_K`). If you hit a provider limit, the chat shows a clear message instead of failing silently.

## Tests

```bash
cd backend  && pytest            # API, auth, upload, RAG isolation, streaming (LLM + embeddings are faked)
cd frontend && node --test       # API client and stream parser
```

The backend tests use a temporary database and ChromaDB folder and never call a real LLM API.

## API

All routes except signup, login and `/health` need `Authorization: Bearer <token>`.

| Method | Path | What it does |
|---|---|---|
| POST | `/api/auth/signup` | Create account (JSON: username, password) |
| POST | `/api/auth/login` | Get a token (form fields: username, password) |
| GET | `/api/auth/me` | Current user |
| POST | `/api/documents` | Upload PDF/TXT → `202`, processed in the background |
| GET | `/api/documents` | List your documents with status (`processing` / `ready` / `failed`) |
| DELETE | `/api/documents/{id}` | Delete a document and its chunks |
| POST | `/api/chat/stream` | Ask a question → NDJSON stream of `sources`, `token`…, `done` |
| GET | `/api/chat/history` | Last 100 messages |
| DELETE | `/api/chat/history` | Clear history |
| GET | `/health` | App + database check |

## Deploying

Backend and frontend are separate, so they can live on different hosts.

1. **Database:** create a managed PostgreSQL and use its URL as `DATABASE_URL` (`postgresql+psycopg2://user:password@host:5432/dbname`).
2. **Backend:** deploy `backend/` (it has a Dockerfile) to Render, Railway, Fly.io, etc. Set `SECRET_KEY`, `GROQ_API_KEY` (or the key of the provider you chose), `DATABASE_URL`, and `CORS_ORIGINS` = your frontend's public URL.
   **ChromaDB stores files on disk, so attach a persistent disk/volume and point `CHROMA_PATH` at it.** On a temporary disk, uploaded documents disappear on every restart (the database rows stay but the searchable chunks are lost).
3. **Frontend:** deploy `frontend/` as a static site (or with its Dockerfile) and set `API_BASE_URL` to the backend's public URL. For a plain static host without Docker, edit `frontend/js/config.js` directly.
4. Use HTTPS for both, and never use `allow_origins=["*"]`.

## Known limitations / next steps

- Tables are created with `create_all`; for schema changes in production add **Alembic** migrations.
- One ChromaDB folder means one backend instance. To scale out, move to a hosted vector database.
- The JWT lives in `localStorage` (fine for learning; httpOnly cookies are safer for production).
- Rate limiting is per IP address. Behind a proxy/load balancer configure forwarded headers so users are not all seen as one IP.
- Scanned (image-only) PDFs have no text and are marked `failed`; OCR is not included.
- No answer caching: every answer depends on chat history, so repeats are not identical.
