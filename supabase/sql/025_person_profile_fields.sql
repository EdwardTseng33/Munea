-- 2026-07-24：開帳與個人資料重整——persons 延伸暱稱/生日/地區欄位。
-- 個人資料卡（web/index.html #profileModal）原本 pfSave 只寫 localStorage，換裝置/換手機資料就不見；
-- 這批欄位讓 Brain /person-profile 接口能把同一份資料寫回雲端，App 開機時「較新者勝」合併回本機。
-- 刻意不重用既有 persons.display_name（該欄位目前實際存的是 AI 陪伴角色名稱、不是使用者本人名字，
-- 是 bootstrap_account_response 既有行為——這裡不動它，另開 profile_name 欄位存使用者本人名稱，避免混淆）。
-- 沿用既有 persons RLS（persons_account_member_all：帳號成員全權限），不另立新政策。
-- 照片（pfAvatar）不上雲，維持只存本機（隱私面與工程面都小很多，需求單已拍板）。
-- Run after 024_inactive_free_account_retention.sql.

begin;

alter table public.persons
  add column if not exists profile_name text,
  add column if not exists nickname text,
  add column if not exists birth_year smallint,
  add column if not exists birth_month smallint,
  add column if not exists county text,
  add column if not exists district text;

alter table public.persons
  drop constraint if exists persons_birth_month_range;
alter table public.persons
  add constraint persons_birth_month_range
  check (birth_month is null or (birth_month between 1 and 12));

alter table public.persons
  drop constraint if exists persons_birth_year_range;
alter table public.persons
  add constraint persons_birth_year_range
  check (birth_year is null or (birth_year between 1900 and 2100));

commit;
