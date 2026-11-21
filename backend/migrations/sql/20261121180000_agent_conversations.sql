-- Web chat agent (T-086, T-091; PRD FR6.2, FR6.6, AC6.8, AC6.9).
--
-- * `chat_sessions.agent_history`: the last turns of this phone's conversation with the agent,
--   so a plain answer ("keju") fills the question it asked. Free text can hold personal data,
--   so it is stored encrypted (`enc:v1:…`, AES-256-GCM, decrypted by the API only). It goes
--   with the session: idle sessions are purged after 2 hours.
-- * `agent_tool_calls`: one row per tool call — session hash, tool, whether it ran, result size,
--   and duration. Never the arguments, the result, or the customer's text (FR6.6).

alter table app.chat_sessions add column agent_history text
  check (agent_history is null or (agent_history like 'enc:v1:%' and length(agent_history) <= 60000));

create table app.agent_tool_calls (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  session_key_hash  text not null check (session_key_hash ~ '^[0-9a-f]{64}$'),
  message_id        uuid not null,
  prompt_version    text not null check (length(prompt_version) between 1 and 40),
  tool              text not null check (tool ~ '^[a-z_]{1,40}$'),
  outcome           text not null check (outcome in ('ok', 'error', 'refused', 'limit')),
  result_bytes      integer not null default 0 check (result_bytes >= 0),
  duration_ms       integer not null default 0 check (duration_ms >= 0),
  created_at        timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);
create index on app.agent_tool_calls (outlet_id, created_at);

alter table app.agent_tool_calls enable row level security;
create policy outlet_scope on app.agent_tool_calls to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id));
create policy no_device on app.agent_tool_calls as restrictive to app_backend
  using (app.current_actor() is distinct from 'device')
  with check (app.current_actor() is distinct from 'device');
-- Append-only log.
grant select, insert on app.agent_tool_calls to app_backend;
