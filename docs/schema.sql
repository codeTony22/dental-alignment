-- ============================================================
--  Dental implant case portal — core schema (Postgres / Supabase)
--
--  PII-free by design: no patient names, DOB, or contact info.
--  Doctors reference their own cases via an opaque label only,
--  and keep the patient mapping on their own side.
--
--  Field choices mirror the RealGUIDE "Register Scan Abutment"
--  workflow: per-tooth implant system + code + scan-body type,
--  and crown/bridge restorations (e.g. single crowns at 26/28,
--  a 23-24 bridge).
-- ============================================================


-- ----------------------------------------------------------------
--  Enums
-- ----------------------------------------------------------------

create type case_status as enum (
  'draft',        -- doctor is still filling it out
  'submitted',    -- handed off, awaiting processing
  'in_design',    -- being worked (human technician or pipeline)
  'ready',        -- deliverable produced, awaiting payment
  'delivered',    -- paid + downloaded
  'rejected'      -- unworkable scan / cancelled
);

create type job_status as enum (
  'queued', 'running', 'needs_review', 'failed', 'completed'
);

create type restoration_kind as enum (
  'single_crown', 'bridge', 'abutment_only'
);

create type arch_type as enum ('upper', 'lower');

create type scan_file_kind as enum (
  'lower_arch',   -- intraoral / model scan, lower
  'upper_arch',   -- intraoral / model scan, upper / antagonist
  'scan_bodies',  -- arch captured with scan bodies in place
  'bite',         -- occlusion / buccal bite
  'waxup',        -- diagnostic wax-up
  'other'
);


-- ----------------------------------------------------------------
--  Profiles (1:1 with Supabase auth.users)
-- ----------------------------------------------------------------

create table profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  clinic_name  text,
  created_at   timestamptz not null default now()
);


-- ----------------------------------------------------------------
--  Cases  (one per restoration job; NO patient PII)
-- ----------------------------------------------------------------

create table cases (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null references profiles (id) on delete cascade,
  doctor_case_ref text not null,                       -- doctor's own label, not patient data
  tooth_notation  text not null default 'universal',   -- 'universal' | 'fdi'
  notes           text,
  status          case_status not null default 'draft',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index cases_owner_idx on cases (owner_id);
create index cases_status_idx on cases (status);


-- ----------------------------------------------------------------
--  Implant sites  (one row per implant — e.g. 23, 24, 26, 28)
-- ----------------------------------------------------------------

create table implant_sites (
  id             uuid primary key default gen_random_uuid(),
  case_id        uuid not null references cases (id) on delete cascade,
  arch           arch_type not null,
  tooth_number   int not null,            -- e.g. 23 (universal numbering)
  implant_system text not null,           -- library folder, e.g. "DG code lite for zimmer and Bio"
  implant_code   text not null,           -- e.g. "zimmer 3.5 dg code 5020"
  scan_body_type text not null,           -- e.g. "atlantic scan body"
  created_at     timestamptz not null default now(),
  unique (case_id, tooth_number)
);

create index implant_sites_case_idx on implant_sites (case_id);


-- ----------------------------------------------------------------
--  Restorations  (single crown, or bridge spanning teeth)
-- ----------------------------------------------------------------

create table restorations (
  id            uuid primary key default gen_random_uuid(),
  case_id       uuid not null references cases (id) on delete cascade,
  kind          restoration_kind not null,
  tooth_numbers int[] not null,           -- [26] single crown, [23,24] bridge span
  material      text,                     -- optional, e.g. zirconia
  created_at    timestamptz not null default now()
);

create index restorations_case_idx on restorations (case_id);


-- ----------------------------------------------------------------
--  Uploaded scan files  (objects live in private storage)
-- ----------------------------------------------------------------

create table case_files (
  id          uuid primary key default gen_random_uuid(),
  case_id     uuid not null references cases (id) on delete cascade,
  kind        scan_file_kind not null,
  storage_key text not null,              -- object key in S3 / Supabase Storage (private bucket)
  filename    text not null,
  mime_type   text,
  size_bytes  bigint,
  checksum    text,                       -- sha256, for integrity + dedupe
  uploaded_at timestamptz not null default now()
);

create index case_files_case_idx on case_files (case_id);


-- ----------------------------------------------------------------
--  Processing jobs  (Phase 2 handoff)
-- ----------------------------------------------------------------

create table processing_jobs (
  id              uuid primary key default gen_random_uuid(),
  case_id         uuid not null references cases (id) on delete cascade,
  status          job_status not null default 'queued',
  assigned_worker text,
  attempts        int not null default 0,
  result_key      text,                   -- produced deliverable, private bucket
  error           text,
  queued_at       timestamptz not null default now(),
  started_at      timestamptz,
  finished_at     timestamptz
);

create index processing_jobs_case_idx on processing_jobs (case_id);
create index processing_jobs_status_idx on processing_jobs (status);


-- ----------------------------------------------------------------
--  Orders / payment gate
-- ----------------------------------------------------------------

create table orders (
  id                       uuid primary key default gen_random_uuid(),
  case_id                  uuid not null references cases (id) on delete cascade,
  amount_cents             int not null,
  currency                 text not null default 'usd',
  stripe_payment_intent_id text,
  paid                     boolean not null default false,
  paid_at                  timestamptz,
  created_at               timestamptz not null default now()
);

create index orders_case_idx on orders (case_id);


-- ----------------------------------------------------------------
--  updated_at trigger for cases
-- ----------------------------------------------------------------

create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger cases_set_updated_at
  before update on cases
  for each row execute function set_updated_at();


-- ============================================================
--  Row Level Security
--
--  Doctors can touch only their own data. The NestJS backend
--  and the processing workers use the Supabase service role,
--  which bypasses RLS, to drive jobs and unlock downloads.
-- ============================================================

alter table profiles        enable row level security;
alter table cases           enable row level security;
alter table implant_sites   enable row level security;
alter table restorations    enable row level security;
alter table case_files      enable row level security;
alter table processing_jobs enable row level security;
alter table orders          enable row level security;


-- profiles: a user manages only their own profile
create policy "own profile" on profiles
  for all
  using (id = auth.uid())
  with check (id = auth.uid());


-- cases: owner-only, full access
create policy "own cases" on cases
  for all
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());


-- child tables: allowed when the parent case belongs to the user
create policy "own implant_sites" on implant_sites
  for all
  using     (exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()))
  with check(exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()));

create policy "own restorations" on restorations
  for all
  using     (exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()))
  with check(exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()));

create policy "own case_files" on case_files
  for all
  using     (exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()))
  with check(exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()));


-- jobs + orders: doctors may READ status; only the backend writes them.
-- result_key is safe to expose because the bucket is private — the key
-- alone grants nothing. A download URL is signed by the backend only
-- after it confirms orders.paid = true.
create policy "read own jobs" on processing_jobs
  for select
  using (exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()));

create policy "read own orders" on orders
  for select
  using (exists (select 1 from cases c where c.id = case_id and c.owner_id = auth.uid()));
