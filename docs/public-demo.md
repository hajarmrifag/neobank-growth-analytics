# Public transaction demo

The public deployment uses the same FastAPI service and PostgreSQL transfer logic
as the local project, with an additional anonymous sandbox layer. Visitors can
create two fictional accounts, transfer £25, replay the request and try an
insufficient-funds failure through the home page. `/docs` exposes the full API.

## Access and bounded data

- `POST /demo/sessions` returns a random bearer token valid for 30 minutes.
- Only a SHA-256 hash of the token is stored in PostgreSQL.
- Every account read and transfer requires that session's token. Accounts from
  other sessions return 404; both sides of a transfer must belong to the session.
- Idempotency keys are scoped to the session. Session expiry ends the retry window.
- Each session is limited to five accounts, 100 transfers and 60 requests/minute.
- There are at most 200 sessions and 20 new sessions/minute across the service.
- Request bodies are limited to 4 KB; Uvicorn limits concurrent connections/tasks.
- Expired sandbox data is removed every minute and before new-session creation.
  Cleanup uses the same session row locks as mutations. Local-mode accounts with
  no session are never removed by cleanup.
- The browser keeps the token in memory only. A reload requires a new session.
- All data is disposable. Use fictional names; do not submit personal information.

These are portfolio abuse limits, not a production identity system or protection
against a determined denial-of-service attack. A shared service may return 429
or 503 when busy. No real money is accepted or moved.

## Render deployment

`render.yaml` configures one free Docker web service. The Dockerfile is
`Dockerfile.demo`, with health endpoint `/health` and `BANKING_PUBLIC_DEMO=1`.
It uses Python 3.12 and PostgreSQL 16 from their official Docker images. PostgreSQL listens only on a private Unix
socket inside the container; it has no TCP listener or public database port.

The free-demo container deliberately puts PostgreSQL on ephemeral storage.
Restarts/redeployments can clear all sessions and balances. This avoids depending
on an expiring free managed database. The separate-service `compose.api.yml` and
`Dockerfile.api` remain available for persistent local or managed-DB deployments.

Free hosting can sleep when idle. The first request may be slow while it starts.
This is suitable for a synthetic portfolio demo, not durable banking records.

For a Render web service connected by public repository URL:

1. Select `https://github.com/hajarmrifag/neobank-growth-analytics`, branch `main`.
2. Select Docker, Dockerfile path `./Dockerfile.demo`, free instance.
3. Set health check to `/health`; use the default Docker command.
4. Deploy. For later updates, manually deploy the latest commit unless automatic
   deployment has separately been configured.

## Local verification of the hosting image

```bash
docker build -f Dockerfile.demo -t neobank-public-demo .
docker run --rm --name neobank-public-demo -p 127.0.0.1:18000:10000 neobank-public-demo
```

Open `http://localhost:18000/`. The home page is a guided demo; the API docs let
you create a session and paste its token into the Authorize dialog.

The integration suite covers ownership isolation, scoped keys, expired sessions,
cleanup, rate/body limits and concurrent account quotas in addition to the core
transaction tests. Run it with the instructions in [the API guide](banking-api.md).
