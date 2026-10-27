# Customer Support Agent

A Gemini-powered order support chatbot with order lookup, mock refund processing, and human approval for refunds over $50.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirement.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then start the web app:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The API endpoints are `/api/chat`, `/api/approval`, and `/api/reset`.

## Project layout

- `app/` contains application configuration, startup, API routes, and request/response models.
- `agent/` contains the system prompt, policies, and Gemini tool execution loop.
- `tools/` contains order lookup, mock refund processing, and function registration.
- `static/index.html` contains the browser chat interface.

Order data and chat sessions are in memory for this demo. Refund processing is a mock operation and does not issue real payments.