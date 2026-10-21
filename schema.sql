-- ============================================================
-- Agentic CRM — initial schema
-- Target: Postgres 15+ / Supabase
-- Run this whole file once in the Supabase SQL editor.
-- ============================================================

-- ---------- Extensions ----------
create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "vector";     -- pgvector, native on Supabase

-- ---------- Enums ----------
create type account_product   as enum ('savings_account','current_account','credit_card','upi_wallet','personal_loan','nbfc_loan','fixed_deposit');
create type account_status    as enum ('active','closed','dormant');
create type ticket_status     as enum ('open','in_review','pending_approval','resolved','escalated');
create type ticket_priority   as enum ('low','medium','high','critical');
create type deal_type         as enum ('retention_risk','cross_sell');
create type deal_stage        as enum ('identified','in_progress','actioned','closed');
create type activity_type     as enum ('call','email','note','agent_action','status_change');
create type approval_status   as enum ('pending','approved','rejected','edited','auto_approved');
create type user_role         as enum ('admin','agent','reviewer');

-- ---------- Orgs (multi-tenant root) ----------
create table orgs (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

-- ---------- Users ----------
create table app_users (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references orgs(id) on delete cascade,
  email           text not null unique,
  hashed_password text not null,
  role            user_role not null default 'agent',
  created_at      timestamptz not null default now()
);

-- ---------- Contacts (consumers) ----------
create table contacts (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  full_name   text not null,
  email       text,
  phone       text,
  created_at  timestamptz not null default now()
);
create index idx_contacts_org on contacts(org_id);

-- ---------- Accounts (financial products a contact holds) ----------
create table accounts (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  contact_id  uuid not null references contacts(id) on delete cascade,
  product     account_product not null,
  status      account_status not null default 'active',
  opened_at   date not null,
  created_at  timestamptz not null default now()
);
create index idx_accounts_contact on accounts(contact_id);

-- ---------- Grievance taxonomy (seeded from real NCH categories) ----------
create table grievance_categories (
  id             uuid primary key default gen_random_uuid(),
  category_name  text not null unique,
  sector         text not null default 'banking',
  source         text not null default 'National Consumer Helpline',
  typical_share  numeric(5,2)   -- approximate real-world share, used to weight synthetic generation
);

-- ---------- Tickets (complaints) ----------
create table tickets (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references orgs(id) on delete cascade,
  contact_id            uuid not null references contacts(id) on delete cascade,
  account_id            uuid references accounts(id) on delete set null,
  category_id           uuid not null references grievance_categories(id),
  -- Immutable ground-truth label for the eval harness, set once at seed time
  -- and never touched again. category_id is the *live* value the triage
  -- agent's proposals can overwrite once a human approves them (see
  -- review_actions.py) -- if eval accuracy were measured against category_id
  -- instead, every approved/edited triage proposal would silently turn that
  -- ticket into a row that trivially "matches" its own agent's prediction,
  -- inflating the metric more with every review session.
  seeded_category_id    uuid not null references grievance_categories(id),
  company               text not null,
  narrative             text not null,
  status                ticket_status not null default 'open',
  priority              ticket_priority not null default 'medium',
  date_received         timestamptz not null default now(),
  regulatory_deadline   timestamptz,   -- set by trigger below: date_received + 30 days (RBI RB-IOS clock)
  resolved_at           timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index idx_tickets_org on tickets(org_id);
create index idx_tickets_contact on tickets(contact_id);
create index idx_tickets_deadline on tickets(regulatory_deadline) where status <> 'resolved';

-- timestamptz arithmetic isn't immutable, so this can't be a generated column —
-- a trigger is the standard workaround.
create or replace function set_regulatory_deadline()
returns trigger as $$
begin
  if new.regulatory_deadline is null then
    new.regulatory_deadline := new.date_received + interval '30 days';
  end if;
  return new;
end;
$$ language plpgsql;

create trigger trg_set_regulatory_deadline
  before insert on tickets
  for each row execute function set_regulatory_deadline();

-- ---------- Deals (retention risk / cross-sell opportunities) ----------
create table deals (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  contact_id  uuid not null references contacts(id) on delete cascade,
  type        deal_type not null,
  stage       deal_stage not null default 'identified',
  notes       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index idx_deals_contact on deals(contact_id);

-- ---------- Activities (interaction timeline) ----------
create table activities (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  contact_id  uuid references contacts(id) on delete cascade,
  ticket_id   uuid references tickets(id) on delete cascade,
  deal_id     uuid references deals(id) on delete cascade,
  type        activity_type not null,
  content     text,
  created_at  timestamptz not null default now()
);
create index idx_activities_ticket on activities(ticket_id);
create index idx_activities_deal on activities(deal_id);

-- ---------- Agent action log (the audit trail — core of the "agentic" story) ----------
create table agent_actions (
  id                  uuid primary key default gen_random_uuid(),
  org_id              uuid not null references orgs(id) on delete cascade,
  ticket_id           uuid references tickets(id) on delete cascade,
  deal_id             uuid references deals(id) on delete cascade,
  agent_name          text not null,        -- 'triage' | 'sales_copilot' | 'rag_answer' | 'follow_up'
  action_type         text not null,        -- 'classify' | 'draft_response' | 'escalate' | 'schedule_followup' ...
  input_summary       text,
  proposed_output     text,
  final_output         text,                -- what actually went out, after any human edit
  tool_calls          jsonb,
  confidence          numeric(4,3),
  requires_approval   boolean not null default true,
  approval_status     approval_status not null default 'pending',
  approved_by         uuid references app_users(id),
  created_at          timestamptz not null default now(),
  resolved_at         timestamptz
);
create index idx_agent_actions_ticket on agent_actions(ticket_id);
create index idx_agent_actions_pending on agent_actions(approval_status) where approval_status = 'pending';

-- ---------- Knowledge base (RAG source docs) ----------
create table kb_documents (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  title       text not null,
  source      text not null,   -- e.g. 'RBI RB-IOS 2026'
  created_at  timestamptz not null default now()
);

create table kb_chunks (
  id            uuid primary key default gen_random_uuid(),
  document_id   uuid not null references kb_documents(id) on delete cascade,
  chunk_index   int not null,
  chunk_text    text not null,
  embedding     vector(384)   -- matches MiniLM-style embedding dimension
);
-- No ANN index (ivfflat/hnsw) yet: ivfflat's clustering is unreliable well below
-- ~1000 rows (an under-populated 'lists' partition can return zero candidates for
-- a query that has an obvious exact match -- observed firsthand at 88 rows, where
-- some queries returned 0 results with lists=100 despite a clear top-3 match
-- existing). At this KB's current size, an exact sequential scan is both correct
-- and fast. Revisit (ivfflat with lists ~= rows/1000, or hnsw) once the corpus
-- grows into the thousands of chunks.

-- ============================================================
-- Seed: real NCH grievance categories (approximate shares,
-- derived from public consumerhelpline.gov.in dashboard samples)
-- ============================================================
insert into grievance_categories (category_name, sector, typical_share) values
  ('Amount debited without user consent',                         'banking', 16.5),
  ('Wrongly transferred amount to another account',                'banking', 12.0),
  ('Delay or denial of service',                                   'banking', 16.0),
  ('Account blocked or held without informing consumer',           'banking', 9.8),
  ('Fraudulent transaction — money invested via website/app',      'banking', 4.1),
  ('Fraudulent transaction — link/OTP/QR code sharing',             'banking', 1.5),
  ('Amount debited but not dispensed from ATM',                     'banking', 4.1),
  ('Online transaction failed or delayed but amount debited',       'banking', 4.6),
  ('Charges debited for not maintaining minimum balance',           'banking', 4.6),
  ('Misbehaviour or misselling by bank staff/agent',                'banking', 2.6),
  ('Delay in issuance of debit card/cheque book/statement',         'banking', 2.5),
  ('Insurance policy issued without consent',                       'banking', 2.2),
  ('Excess or unnotified service charges',                          'banking', 2.2),
  ('Delay in activation of inactive account',                       'banking', 2.0),
  ('Delay in processing or disbursement of loan',                   'banking', 1.8),
  ('Refund or cashback not credited',                               'banking', 1.7),
  ('KYC details not linked or incorrectly updated',                 'banking', 1.3),
  ('Promotional or recovery calls received from bank',              'banking', 0.9),
  ('Other',                                                         'banking', 9.6);
