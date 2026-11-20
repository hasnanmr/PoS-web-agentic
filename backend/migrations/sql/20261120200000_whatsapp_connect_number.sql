-- T-045: connect an outlet to its Meta WhatsApp phone number (outlet-number mapping, FR2.10).
-- Until the owner-facing setup (O12, Embedded Signup, T-100) exists, a platform operator runs
-- this through the CLI (`app.cli whatsapp-connect`). It is a definer function because the
-- operator has no tenant context. Passing an empty phone number id disconnects the outlet.

create function app.connect_outlet_whatsapp(
  p_outlet_id uuid,
  p_phone_number_id text,
  p_whatsapp_phone text default null
) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_tenant uuid;
  v_number text := nullif(trim(p_phone_number_id), '');
begin
  update app.outlets
     set whatsapp_phone_number_id = v_number,
         whatsapp_phone = coalesce(nullif(trim(p_whatsapp_phone), ''), whatsapp_phone),
         whatsapp_status = case when v_number is null then 'not_started' else 'connected' end
   where id = p_outlet_id
  returning tenant_id into v_tenant;
  if v_tenant is null then
    raise exception 'outlet % not found', p_outlet_id using errcode = 'P0002';
  end if;
  insert into app.audit_events (tenant_id, outlet_id, actor_type, action, entity_type, entity_id, data)
  values (v_tenant, p_outlet_id, 'system',
          case when v_number is null then 'outlet.whatsapp_disconnected'
               else 'outlet.whatsapp_connected' end,
          'outlet', p_outlet_id::text,
          jsonb_build_object('phone_number_id', v_number));
end $$;

revoke execute on function app.connect_outlet_whatsapp(uuid, text, text) from public;
grant execute on function app.connect_outlet_whatsapp(uuid, text, text) to app_backend;
