-- T-010, T-012: owner onboarding (O1) and staff invitations (O4).
--
-- An invited owner has no tenant yet, so RLS cannot let app_backend insert the
-- tenant, the owner row, and the first outlet. complete_owner_onboarding() does
-- it with definer rights, only for the caller's own open invitation, in one
-- transaction. Everything after onboarding goes through RLS as usual.

create function app.complete_owner_onboarding(
  p_auth_user_id   uuid,
  p_business_name  text,
  p_business_type  app.tenant_type,
  p_outlet_name    text,
  p_timezone       text,
  p_address        text,
  p_whatsapp_phone text
) returns table (tenant_id uuid, outlet_id uuid)
language plpgsql volatile security definer set search_path = '' as $$
declare
  inv      record;
  v_tenant uuid;
  v_outlet uuid;
begin
  select id, email into inv from app.owner_invitations
  where auth_user_id = p_auth_user_id and accepted_at is null and revoked_at is null
  for update;
  if not found then
    raise exception 'no open owner invitation' using errcode = 'P0002';
  end if;

  insert into app.tenants (name, type) values (trim(p_business_name), p_business_type)
  returning id into v_tenant;

  insert into app.users (id, tenant_id, email, display_name, role, invited_at, invitation_accepted_at)
  values (p_auth_user_id, v_tenant, inv.email, split_part(inv.email, '@', 1), 'owner', now(), now());

  insert into app.outlets (tenant_id, name, timezone, address, whatsapp_phone, order_prefix)
  values (v_tenant, trim(p_outlet_name), coalesce(p_timezone, 'Asia/Jakarta'),
          nullif(trim(p_address), ''), nullif(trim(p_whatsapp_phone), ''), 'A')
  returning id into v_outlet;

  update app.owner_invitations set accepted_at = now(), tenant_id = v_tenant where id = inv.id;

  insert into app.audit_events (tenant_id, actor_type, actor_id, action, entity_type, entity_id, data)
  values (v_tenant, 'user', p_auth_user_id, 'tenant.created', 'tenant', v_tenant::text,
          jsonb_build_object('outlet_id', v_outlet, 'invitation_id', inv.id));

  return query select v_tenant, v_outlet;
end $$;

revoke execute on function app.complete_owner_onboarding(uuid, text, app.tenant_type, text, text, text, text) from public;
grant execute on function app.complete_owner_onboarding(uuid, text, app.tenant_type, text, text, text, text) to app_backend;

-- Emails are unique across all tenants (users_email_key), but RLS hides other
-- tenants' users. This lets an owner learn only "taken or not" before inviting.
create function app.email_registered(p_email text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from app.users where lower(email) = lower(trim(p_email)))
      or exists (select 1 from app.owner_invitations
                 where lower(email) = lower(trim(p_email)) and revoked_at is null)
$$;

revoke execute on function app.email_registered(text) from public;
grant execute on function app.email_registered(text) to app_backend;
