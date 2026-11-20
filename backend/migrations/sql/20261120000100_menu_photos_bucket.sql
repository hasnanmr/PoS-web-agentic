-- T-132: private Supabase Storage bucket for menu photos (O5 "Foto *", shown in S1 and the
-- O5 list). The API uploads and signs objects with the service role key; browsers only get
-- short-lived signed URLs, so the bucket has no public access and no policies for the
-- anon/authenticated roles. Object path: <tenant_id>/<product_id>/<random>.<ext>, stored in
-- app.products.photo_path (column from T-004).
-- Plain PostgreSQL (CI, local tests) has no storage schema: the bucket is skipped there.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values ('menu-photos', 'menu-photos', false, 5242880,
            array['image/jpeg', 'image/png', 'image/webp'])
    on conflict (id) do update
      set public = false,
          file_size_limit = excluded.file_size_limit,
          allowed_mime_types = excluded.allowed_mime_types;
  end if;
end $$;
