# Deploying NovaPay

Everything in this repo is built and verified locally (Docker images build,
and the API container was run against the live Supabase DB and answered
real requests). What's left needs your accounts, not more code.

## 1. Push to GitHub

```
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin master
```

(Create the empty repo on GitHub first, or via `gh repo create` if you
install the GitHub CLI.)

## 2. Create a Render account and connect it to GitHub

https://dashboard.render.com -> sign up / log in -> connect your GitHub
account and grant it access to this repo.

## 3. Deploy via the Blueprint

New -> Blueprint -> pick this repo. Render reads `render.yaml` and proposes
two services: `novapay-api`, `novapay-frontend`. Both are on the free plan.
Review field names against Render's current UI before accepting --
`render.yaml` wasn't tested against a live Render deploy, it's a starting
point, not a guarantee.

If the Blueprint flow doesn't match what you see, create the two web
services by hand instead, using the same Dockerfile paths and env vars
listed below -- the blueprint is a shortcut, not a requirement.

Deliberately not included: a cron service for the agent runner
(`Dockerfile.agents`). Render's cron jobs have a $1/month minimum even on
the free plan -- see §6 for running the agents without paying for that.

## 4. Fill in secrets (Render dashboard, not render.yaml)

On `novapay-api`:
| Key | Value |
|---|---|
| `DATABASE_URL` | the same pooler URL from your local `.env` |
| `GROQ_API_KEY` | from your local `.env` |
| `JWT_SECRET` | from your local `.env` -- reusing it keeps existing tokens valid, but a fresh one works too since all it does is invalidate old sessions |

On `novapay-api` only: `ALLOWED_ORIGINS` -- set to the frontend's actual
Render URL once you know it (Render assigns it from the service name, so
it's usually predictable before the first deploy finishes, but confirm it).

On `novapay-frontend`: `API_BASE_URL` -- set to the api service's actual
Render URL. This is read at container start (see `frontend/entrypoint.sh`),
not baked in at build time, so changing it later is a redeploy away, not a
rebuild.

## 5. Verify

```
curl https://<your-api>.onrender.com/health
```

should return `{"status":"ok"}`. Then open the frontend URL and log in with
the admin account from `create_admin_user.py` (or create a fresh one by
running that script locally against the production `DATABASE_URL`).

## 6. Running the agents

**Triage runs automatically.** A customer submitting a complaint via
`/submit-complaint` triggers `run_triage` as a FastAPI background task right
after the API responds -- see `api/routers/public.py`. It still only writes
a pending `agent_action`; nothing bypasses the approval queue. This is the
one agent worth auto-triggering, since it's naturally tied to a single
event (a new ticket existing).

**Follow-up and sales-copilot stay manual**, to avoid Render's $1/month cron
minimum -- those are about aging state over time (a deadline getting close,
a deal worth nudging), not a single event, so there's no clean request to
hang them off of. Run them from your own machine, pointed at the production
database, whenever you want fresh proposals for the demo:

```
docker build -t crm-agents -f Dockerfile.agents .
docker run --rm --env-file .env crm-agents python run_followup_sweep.py
docker run --rm --env-file .env crm-agents python run_sales_copilot.py
```

(`run_triage.py` still works the same way too, for triaging already-seeded
tickets that predate this change.)

`.env` here is your local one -- it already has the production
`DATABASE_URL` (Supabase doesn't distinguish "local" vs "prod", there's only
the one hosted instance). If you later want this automatic, revisit the
$1/month cron job or the Cloud Run + Cloud Scheduler path discussed earlier.
