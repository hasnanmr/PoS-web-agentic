-- Add-on groups with several choices can cap how many options a customer picks
-- (wireframe C3 "Tambahan · opsional, maks 2", O5 group list "maks 2").
--
-- * `max_select`: null = no cap (any number of options); only for `selection = 'multiple'`
--   groups, 2..10 (a single-choice group is always "pilih 1"; 10 is the option limit).
-- * Checked again by the server when an order is priced (`addon_invalid`).

alter table app.addon_groups add column max_select smallint
  check (max_select is null or max_select between 2 and 9);

alter table app.addon_groups add constraint addon_groups_max_select_multiple
  check (max_select is null or selection = 'multiple');
