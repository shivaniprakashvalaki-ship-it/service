-- Run ONCE in Supabase Dashboard > SQL Editor.  Project: veivaeudhxwgpsuxywws

-- 1) Buckets -----------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit)
values ('photos', 'photos', true, 2097152),        -- provider photos: public, 2 MB
       ('documents', 'documents', false, 5242880)  -- verification documents: PRIVATE, 5 MB
on conflict (id) do update
  set public = excluded.public, file_size_limit = excluded.file_size_limit;

-- 2) Policies ----------------------------------------------------------------
-- ONLY needed if the server uses the PUBLISHABLE key (i.e. SUPABASE_SECRET_KEY is NOT set).
-- If you set SUPABASE_SECRET_KEY on the server, SKIP this whole section: the secret key
-- bypasses policies, and the private 'documents' bucket then stays closed to everyone else.
--
-- WARNING: with the policies below, anyone holding the publishable key can list/download/delete
-- objects in 'documents' (the key is meant to be public). That exposes ID proofs. Use the
-- secret key in production.

drop policy if exists "hs_photos_insert" on storage.objects;
drop policy if exists "hs_photos_delete" on storage.objects;
drop policy if exists "hs_documents_insert" on storage.objects;
drop policy if exists "hs_documents_select" on storage.objects;
drop policy if exists "hs_documents_delete" on storage.objects;

create policy "hs_photos_insert" on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'photos');
create policy "hs_photos_delete" on storage.objects for delete to anon, authenticated
  using (bucket_id = 'photos');

create policy "hs_documents_insert" on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'documents');
create policy "hs_documents_select" on storage.objects for select to anon, authenticated
  using (bucket_id = 'documents');
create policy "hs_documents_delete" on storage.objects for delete to anon, authenticated
  using (bucket_id = 'documents');
