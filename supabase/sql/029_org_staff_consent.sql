-- 2026-10-29：機構端專區第 2 段（PR-a）——照護人員身分、機構照護模式同意、席次分點標籤、客戶類型。
-- 設計書：docs/後台-B2B2C-產品框架設計-2026-10-28.md（第 2 節五層結構、第 3 節資料邊界、第 6 節 Q1／Q3／Q6 拍板）。
--
-- 三條不能讓步的鐵線，資料層就要看得出來：
-- 1. 機構端永遠透過「席次」反查長輩，不直接碰 accounts／persons——所以同意表綁 seat_id，不綁人。
-- 2. 沒同意的長輩在機構端查詢裡根本不會被撈出來（硬門，不是遮名字）——所以同意是獨立一張表、
--    預設沒有列＝沒同意；程式用 inner join／in.(...) 只拿 granted 的席次。
-- 3. 機構人員是「真身分」（Q3 B：跟 App 同一套 Supabase Auth），可停用、可稽核到人——
--    所以 org_staff.auth_user_id 參照 auth.users，不是另一套帳密。
--
-- 跟 020 同一個原則：這些表是服務端（service role）專用，anon／authenticated 一律不開——
-- RLS 開著＋零 policy＝一律拒絕。機構人員登入後拿到的是 Supabase Auth 的身分證，
-- 不是直接查表的權限；誰能看哪家、哪一位，全在 engine/org_api.py 一處做對。
-- Run after 028_person_country.sql.

begin;

-- 2.1 客戶類型：care（照護機構，走 L0–L2）／esg（企業員工福利，永遠只有 L0）。
--     企業 HR 窗口＝「機構管理者 − 個人層權限」，用客戶類型切、不另立角色（設計書 2.2）。
alter table public.enterprise_clients
  add column if not exists client_kind text not null default 'care';
alter table public.enterprise_clients drop constraint if exists enterprise_clients_client_kind_check;
alter table public.enterprise_clients
  add constraint enterprise_clients_client_kind_check
  check (client_kind in ('care', 'esg'));

-- 2.2 分點（Q6 A）：第一版做成席次上的標籤，不另開表。空值＝這家沒分分點。
alter table public.enterprise_seats
  add column if not exists site_label text;
create index if not exists enterprise_seats_site_label_idx
  on public.enterprise_seats(enterprise_client_id, site_label) where site_label is not null;

-- 2.3 org_staff — 會登入機構專區的人（設計書 2.2 角色）
--   role：org_admin（機構管理者）／case_manager（社工・個管）／care_worker（照服員）
--   status：invited（我們或管理者開好、本人還沒登入過）→ active（第一次用 Google／Apple 登入、email 對上後綁 auth_user_id）→ disabled
--   email 是邀請鑰匙：第一次登入時以 Supabase Auth 回來的 email（小寫）對上才綁；同一家底下 email 不可重複。
create table if not exists public.org_staff (
  id uuid primary key default gen_random_uuid(),
  enterprise_client_id uuid not null references public.enterprise_clients(id) on delete cascade,
  email text not null,
  auth_user_id uuid references auth.users(id) on delete set null,
  display_name text not null default '',
  role text not null default 'case_manager' check (role in ('org_admin', 'case_manager', 'care_worker')),
  site_label text,
  status text not null default 'invited' check (status in ('invited', 'active', 'disabled')),
  invited_by text not null default 'admin',
  invited_at timestamptz not null default now(),
  activated_at timestamptz,
  disabled_at timestamptz,
  last_login_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists org_staff_client_email_uidx
  on public.org_staff(enterprise_client_id, lower(email));
-- 一個登入身分只能是一家機構的人（跨機構要用不同帳號；避免 A 家的人換個頁籤就看到 B 家）。
create unique index if not exists org_staff_auth_user_uidx
  on public.org_staff(auth_user_id) where auth_user_id is not null;
create index if not exists org_staff_client_idx on public.org_staff(enterprise_client_id, status);

-- 2.4 org_care_consents — 「機構照護模式」同意（Q1 A）。一個席次一列、沒有列＝沒同意。
--   status：granted／revoked；撤回不刪列（留 revoked_at 當事實），再打開就改回 granted 並更新 granted_at。
--   granted_by_role：self（長輩本人）／family（同帳號的家人）——誰按的要留下來，個資法要問得出來。
--   每次切換另外在 audit_events 留一筆（org_consent_granted／org_consent_revoked），這裡只放現況。
create table if not exists public.org_care_consents (
  id uuid primary key default gen_random_uuid(),
  enterprise_client_id uuid not null references public.enterprise_clients(id) on delete cascade,
  seat_id uuid not null references public.enterprise_seats(id) on delete cascade,
  account_id uuid not null references public.accounts(id) on delete cascade,
  status text not null default 'granted' check (status in ('granted', 'revoked')),
  scope text not null default 'care_week' check (scope in ('care_week')),
  granted_by_auth_user_id uuid references auth.users(id) on delete set null,
  granted_by_role text not null default 'family' check (granted_by_role in ('self', 'family')),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  revoked_by_auth_user_id uuid references auth.users(id) on delete set null,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists org_care_consents_seat_uidx on public.org_care_consents(seat_id);
create index if not exists org_care_consents_client_status_idx
  on public.org_care_consents(enterprise_client_id, status);
create index if not exists org_care_consents_account_idx on public.org_care_consents(account_id);

drop trigger if exists org_staff_set_updated_at on public.org_staff;
create trigger org_staff_set_updated_at
  before update on public.org_staff
  for each row execute function public.set_updated_at();

drop trigger if exists org_care_consents_set_updated_at on public.org_care_consents;
create trigger org_care_consents_set_updated_at
  before update on public.org_care_consents
  for each row execute function public.set_updated_at();

alter table public.org_staff enable row level security;
alter table public.org_care_consents enable row level security;

-- 服務端專用：不對 anon／authenticated 開任何 grant、不建任何 policy（同 020）。
revoke all on public.org_staff from anon, authenticated;
revoke all on public.org_care_consents from anon, authenticated;

commit;
