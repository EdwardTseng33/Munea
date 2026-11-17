-- Munea 企業席次 — 開通碼（2026-11-17 · Edward 拍板）。
-- Run after 020_enterprise_seats.sql（enterprise_seats）與 030_org_staff_consent.sql（site_label）。
--
-- 為什麼要有開通碼：
--   020 的席次只認 invite_email，靠「機構給的 email＝使用者登入 App 的 email」對人。
--   11/17 查正式庫 14 個帳號：9 個用 Apple 登入、其中 6 個是蘋果的隱藏信箱
--   （@privaterelay.appleid.com）——機構名單上的真信箱永遠對不上；手機號碼 0 筆
--   （App 沒有手機登入、也沒有地方填）。而且 020 沒有「名單先匯入、之後才註冊」的補對機制，
--   pending 席次不會自己變 active。
--   開通碼把「這個席次是誰的」交給持碼的人自己認領：機構拿到一批 8 位數字的碼發給長輩，
--   長輩登入 App 後輸入，席次就綁到他的帳號——不管他用 Google、Apple 還是隱藏信箱登入。
--
-- 欄位：
--   redeem_code   8 位數字（長輩好輸入）；每席一組、全表唯一；null＝這席走舊的 email 對人。
--   member_name   機構名冊上的稱呼（選填）。只給後台與機構窗口認人用，系統不拿來驗證。
--   member_phone  機構名冊上的手機（選填）。同上：認人用，不發簡訊、不當登入識別。
--   redeemed_at   開通碼被輸入、席次綁到帳號的時間。
--
-- 個資：member_name／member_phone 由機構提供，跟 020 其餘欄位一樣只有 service role 讀得到
-- （RLS 開著、零 policy）；機構專區（/org/*、portal 摘要）不得帶出這兩欄與 redeem_code。

begin;

-- 開通碼席次沒有 email。唯一索引 enterprise_seats_client_email_uidx 在 null 上不衝突
--（Postgres 的 unique 把 null 視為彼此不同），所以同一家公司可以有多席 email 為 null。
alter table public.enterprise_seats alter column invite_email drop not null;

alter table public.enterprise_seats
  add column if not exists redeem_code text,
  add column if not exists member_name text,
  add column if not exists member_phone text,
  add column if not exists redeemed_at timestamptz;

alter table public.enterprise_seats drop constraint if exists enterprise_seats_redeem_code_format;
alter table public.enterprise_seats
  add constraint enterprise_seats_redeem_code_format
  check (redeem_code is null or redeem_code ~ '^[0-9]{8}$');

-- 每席至少要有一種認人方式：email 或開通碼。兩個都沒有＝永遠開不了通的幽靈席次。
alter table public.enterprise_seats drop constraint if exists enterprise_seats_identity_present;
alter table public.enterprise_seats
  add constraint enterprise_seats_identity_present
  check (invite_email is not null or redeem_code is not null);

-- 全表唯一（不是每家公司內唯一）：長輩只輸入碼、不選公司，碼本身就要能找到唯一一席。
create unique index if not exists enterprise_seats_redeem_code_uidx
  on public.enterprise_seats(redeem_code) where redeem_code is not null;

commit;
