-- T-004: WhatsApp customers, consent, conversations, messages, duplicate check.
-- Personal data lives only in these tables (FR12.4). Ledger and stock tables
-- reference a contact id at most, never names, phones, or addresses.

create table app.whatsapp_contacts (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenants (id),
  phone          text,                       -- null after anonymization
  display_name   text,
  is_anonymized  boolean not null default false,
  anonymized_at  timestamptz,
  first_seen_at  timestamptz not null default now(),
  last_inbound_at timestamptz,               -- for the 24-hour customer service window
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (id, tenant_id),
  constraint anonymized_has_no_pii check (not is_anonymized or (phone is null and display_name is null))
);
create unique index whatsapp_contacts_phone_key on app.whatsapp_contacts (tenant_id, phone) where phone is not null;

create table app.customer_addresses (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null,
  contact_id  uuid not null,
  address     text not null,
  created_at  timestamptz not null default now(),
  foreign key (contact_id, tenant_id) references app.whatsapp_contacts (id, tenant_id) on delete cascade
);

-- Consent history per tenant (FR12.1). Latest row is the current state.
create table app.customer_consents (
  id                     bigint generated always as identity primary key,
  tenant_id              uuid not null,
  contact_id             uuid not null,
  status                 app.consent_status not null,
  privacy_notice_version text not null,
  via_outlet_id          uuid,
  created_at             timestamptz not null default now(),
  foreign key (contact_id, tenant_id) references app.whatsapp_contacts (id, tenant_id) on delete cascade
);
create index on app.customer_consents (contact_id, created_at desc);

create table app.conversations (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  outlet_id     uuid not null,
  contact_id    uuid not null,
  flow          text,                -- current bot flow, e.g. 'order', 'reservation'
  state         jsonb not null default '{}'::jsonb,
  updated_at    timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  unique (outlet_id, contact_id),
  unique (id, tenant_id),
  foreign key (outlet_id, tenant_id)  references app.outlets (id, tenant_id),
  foreign key (contact_id, tenant_id) references app.whatsapp_contacts (id, tenant_id)
);

create table app.messages (
  id               bigint generated always as identity primary key,
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  conversation_id  uuid not null,
  direction        app.message_direction not null,
  meta_message_id  text,
  message_type     text not null,      -- text, interactive, order, image, template, ...
  template_name    text,
  body             jsonb not null default '{}'::jsonb,
  status           text,               -- outbound delivery status from Meta
  created_at       timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (conversation_id, tenant_id) references app.conversations (id, tenant_id) on delete cascade
);
create index on app.messages (conversation_id, created_at);
create unique index messages_meta_id_key on app.messages (meta_message_id) where meta_message_id is not null;

-- Duplicate check for inbound processing (NFR8). Inserted in the same
-- transaction as the business change; a conflict means "already processed".
create table app.processed_messages (
  meta_message_id text primary key,
  tenant_id       uuid not null,
  outlet_id       uuid not null,
  processed_at    timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

create trigger touch before update on app.whatsapp_contacts for each row execute function app.touch_updated_at();
create trigger touch before update on app.conversations     for each row execute function app.touch_updated_at();
