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
`/submit-complaint` runs the LangGraph router (`agents/graph.py`) as a FastAPI
background task right after the API responds -- see `api/routers/public.py`.
For a new ticket the router picks the triage agent. It still only writes a
pending `agent_action`; nothing bypasses the approval queue. This is the
one agent worth auto-triggering, since it's naturally tied to a single
event (a new ticket existing).

**Follow-up and sales-copilot** are about aging state over time (a deadline
getting close, a deal worth nudging), not a single event, so there's no
request to auto-trigger them from the way triage is. Two ways to run them:

### 6a. Manually (no new accounts needed)

```
docker build -t crm-agents -f Dockerfile.agents .
docker run --rm --env-file .env crm-agents python run_followup_sweep.py
docker run --rm --env-file .env crm-agents python run_sales_copilot.py
```

(`run_triage.py <ticket-id>` runs the same router for one ticket and prints
which agent it chose. Tickets that were imported already categorized, like the
seed data, are skipped by triage and go to follow-up or nothing.)

The follow-up sweep above also goes through the router for each at-risk ticket,
so a customer ticket whose auto-triage failed gets triaged on the next sweep.

### 6b. On an actual schedule, for free -- Google Cloud Run + Cloud Scheduler

Render's cron has a $1/month minimum even on the free plan; Cloud Run Jobs +
Cloud Scheduler are genuinely free at this scale (Cloud Scheduler's free
quota is 3 job definitions per account -- exactly enough for the two agents
below plus headroom). This needs a Google Cloud account with a card on file
(not charged while under quota) and the `gcloud` CLI, neither of which I can
set up for you. Once you have both:

```bash
# One-time setup
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Build the agent-runner image via Cloud Build (no local Docker-to-GCP auth needed)
gcloud artifacts repositories create crm --repository-format=docker --location=us-central1
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/crm/agents -f Dockerfile.agents .

# Secrets: copy gcp-env-vars.yaml.example -> gcp-env-vars.yaml, fill in
# DATABASE_URL / GROQ_API_KEY / GROQ_API_KEY_2 from your local .env (gitignored)

# One Cloud Run Job per agent, each overriding the image's default command
gcloud run jobs create novapay-followup \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/crm/agents \
  --region us-central1 \
  --env-vars-file gcp-env-vars.yaml \
  --command python --args run_followup_sweep.py \
  --max-retries 1 --task-timeout 300

gcloud run jobs create novapay-salescopilot \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/crm/agents \
  --region us-central1 \
  --env-vars-file gcp-env-vars.yaml \
  --command python --args run_sales_copilot.py \
  --max-retries 1 --task-timeout 300

# Let the default compute service account invoke both jobs
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
for JOB in novapay-followup novapay-salescopilot; do
  gcloud run jobs add-iam-policy-binding $JOB \
    --region us-central1 \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/run.invoker"
done

# Schedule: follow-up every 15 min (deadlines are time-sensitive),
# sales-copilot every 6 hours (cross-sell nudges aren't urgent)
gcloud scheduler jobs create http novapay-followup-schedule \
  --location us-central1 \
  --schedule="*/15 * * * *" \
  --uri="https://run.googleapis.com/v2/projects/YOUR_PROJECT_ID/locations/us-central1/jobs/novapay-followup:run" \
  --http-method POST \
  --oauth-service-account-email ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com

gcloud scheduler jobs create http novapay-salescopilot-schedule \
  --location us-central1 \
  --schedule="0 */6 * * *" \
  --uri="https://run.googleapis.com/v2/projects/YOUR_PROJECT_ID/locations/us-central1/jobs/novapay-salescopilot:run" \
  --http-method POST \
  --oauth-service-account-email ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com
```

Verify a job runs on demand before waiting for the schedule:
`gcloud run jobs execute novapay-followup --region us-central1`, then check
`agent_actions` for a new row the same way the Docker/local tests in this
repo's history did.

These exact flag names came from Google's current docs
([create-jobs](https://docs.cloud.google.com/run/docs/create-jobs),
[jobs-on-schedule](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule))
but weren't run against a live GCP project -- expect to debug a flag or two
against whatever the console shows you.

`.env` here is your local one -- it already has the production
`DATABASE_URL` (Supabase doesn't distinguish "local" vs "prod", there's only
the one hosted instance). If you later want this automatic, revisit the
$1/month cron job or the Cloud Run + Cloud Scheduler path discussed earlier.
