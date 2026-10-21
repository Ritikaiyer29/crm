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
three services: `novapay-api`, `novapay-frontend`, `novapay-agent-sweep`.
Review field names against Render's current UI before accepting --
`render.yaml` wasn't tested against a live Render deploy, it's a starting
point, not a guarantee.

If the Blueprint flow doesn't match what you see, create the two web
services and the cron job by hand instead, using the same Dockerfile paths
and env vars listed below -- the blueprint is a shortcut, not a requirement.

## 4. Fill in secrets (Render dashboard, not render.yaml)

On `novapay-api` and `novapay-agent-sweep`:
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

## 6. What still won't be running

The agent-sweep cron job only runs `run_followup_sweep.py` by default
(`render.yaml`'s `dockerCommand`). Triage and sales-copilot need their own
scheduled job each (same image, different `dockerCommand`) if you want them
running automatically rather than invoked manually.
