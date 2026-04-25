-- TravelDashboard: agentic loop memory tables (Architecture V3)
--
-- Run in Supabase SQL editor. Adjust RLS policies to your app's needs.

create table if not exists agent_sessions (
  session_id uuid primary key default gen_random_uuid(),
  user_id uuid null,
  destination jsonb null,
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now()
);

create index if not exists agent_sessions_user_id_idx on agent_sessions(user_id);

create table if not exists agent_turns (
  turn_id bigserial primary key,
  session_id uuid not null references agent_sessions(session_id) on delete cascade,
  turn_idx integer not null,
  role text not null check (role in ('user','assistant','tool','system')),
  content text not null,
  json_payload jsonb null,
  created_at timestamptz not null default now()
);

create index if not exists agent_turns_session_idx on agent_turns(session_id, turn_idx);

create table if not exists agent_feedback (
  feedback_id bigserial primary key,
  session_id uuid not null references agent_sessions(session_id) on delete cascade,
  user_id uuid null,
  venue_name text null,
  signal_type text not null,
  details jsonb null,
  created_at timestamptz not null default now()
);

create index if not exists agent_feedback_session_idx on agent_feedback(session_id, created_at desc);
create index if not exists agent_feedback_user_idx on agent_feedback(user_id, created_at desc);

create table if not exists user_reco_weights (
  user_id uuid primary key,
  weights jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

