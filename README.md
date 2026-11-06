# Customer Support Agent

A Gemini-powered order support chatbot with order lookup, mock refund processing, and human approval for refunds over $50.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then start the web app:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 to create an account or sign in. The approval dashboard is at http://127.0.0.1:8000/admin.

## Accounts and order data

Create an account from the customer support page with a username and password of at least 8 characters. Passwords are stored as salted PBKDF2 hashes, and login issues an expiring bearer token that is revoked when you sign out.

Orders belong to one user through `orders.user_id`; order lookup and refund processing use the authenticated user's ID. The previous shared demo orders and their refunds are removed when the database is migrated. The app does not seed orders, so only orders associated with a user's ID are available to that account.

Customer API routes (`/api/chat`, `/api/chat/status`, and `/api/reset`) require a bearer token. Account routes are `/api/auth/register`, `/api/auth/token`, `/api/auth/me`, and `/api/auth/logout`.

## Running tests with unittest

This project includes a Python test suite built on the standard library `unittest` framework. To run the application tests directly from the project root:

```bash
python -m unittest tests/test_application.py
```

This command tells Python to load the `unittest` module and execute the test cases defined in `tests/test_application.py`.

## Project layout

- `app/` contains application configuration, startup, API routes, and request/response models.
- `agent/` contains the system prompt, policies, and Gemini tool execution loop.
- `tools/` contains order lookup, mock refund processing, and function registration.
- `static/index.html` contains the browser chat interface.

Order data and chat sessions are in memory for this demo. Refund processing is a mock operation and does not issue real payments.
Only one customer session is supported at a time. The admin dashboard has no authentication and should only be exposed on a trusted local network.