# Backend (FastAPI + LangGraph)

## What this service does

- Accepts URL ingestion requests (article/blog only)
- Scrapes content via **FireCrawl**
- Analyzes content relevance
- Generates platform-specific drafts (Twitter + LinkedIn)
- Selects an image strictly from the article assets
- **Interrupts** for human review in an Agent Inbox
- Routes conditionally based on granular HITL actions
- Verifies OAuth tokens and publishes via APIs only
- Checkpoints state at each interrupt; supports resume

## Tech

- FastAPI
- LangGraph
- SQLite (default) for executions, tokens, and checkpoints
- FireCrawl API (scrape)
- Twitter API + LinkedIn API (publish)

## Setup

### 1) Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure environment

Copy `.env.example` to `.env` and fill values.

```bash
copy .env.example .env
```

You must set:

- `TOKENS_FERNET_KEY` (for encrypted token storage)
- `FIRECRAWL_API_KEY` (for scraping)
- Twitter + LinkedIn OAuth credentials if you want publishing enabled

### 3) Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Core endpoints (high level)

- `POST /v1/executions` — create a new execution from `{ user_id, url }`
- `GET /v1/inbox` — list executions waiting for HITL
- `GET /v1/executions/{execution_id}` — view full state snapshot
- `POST /v1/executions/{execution_id}/actions` — submit HITL actions and resume graph
- `GET /v1/oauth/{provider}/start` — start OAuth (twitter/linkedin)
- `GET /v1/oauth/{provider}/callback` — OAuth callback (stores tokens)

## OAuth quickstart (local)

Open in a browser:

- Twitter: `http://localhost:8000/v1/oauth/twitter/start?user_id=YOUR_USER_ID`
- LinkedIn: `http://localhost:8000/v1/oauth/linkedin/start?user_id=YOUR_USER_ID`

After successful login, you’ll be redirected back to the frontend. Tokens are stored encrypted in SQLite.

## HITL action rules (enforced)

- **Reject Content** → terminate immediately
- **Approve Content + Approve Image** → continue, upload image, publish
- **Approve Content + Reject Image** → continue, publish text only
- **Reject Image only** → continue, publish text only (does not terminate)
- **Regenerate Twitter** → route back to generate Twitter only
- **Regenerate LinkedIn** → route back to generate LinkedIn only
- **Edit Twitter** → update only Twitter post text
- **Edit LinkedIn** → update only LinkedIn post text

## Notes on tokens

- Tokens are obtained via OAuth endpoints (outside LangGraph).
- At publish time, graph only checks token presence/expiry; if invalid → interrupt for re-auth.
- Tokens are stored encrypted-at-rest (Fernet key in env).

