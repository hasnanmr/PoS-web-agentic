-- Security Advisor: fix mutable search paths on app functions. All relations in
-- these functions are already schema-qualified; pg_catalog remains implicit.
alter function app.touch_updated_at() set search_path = '';
alter function app.reject_update_delete() set search_path = '';
alter function app.enforce_addon_option_limit() set search_path = '';
alter function app.current_tenant() set search_path = '';
alter function app.current_user_id() set search_path = '';
alter function app.current_actor() set search_path = '';
alter function app.current_device_outlet() set search_path = '';

-- Hosted Supabase installs this event trigger function in public. It runs as
-- postgres for DDL; Data API roles do not need direct EXECUTE on it. Plain
-- PostgreSQL CI does not have the function, so keep that path conditional.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public;
  end if;
end $$;
