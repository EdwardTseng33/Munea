-- 2026-07-31：個人資料加「國家」欄——四語系上架後，所在地要照國家給對的行政區清單。
-- 台灣用戶完全不受影響（country 空著時一律照舊當台灣處理，App 端也維持縣市→區兩層選單）。
-- 為什麼要存國家而不是從語言推：語言不等於國家（住日本的台灣人介面可能是中文、
-- 住美國的西語家庭介面是西班牙文），推錯會把整份行政區清單給錯，所以存明確的兩碼國別。
-- 同批放寬 county/district 的實際使用長度（程式端上限 20 → 60）：西班牙省名最長 22 字
-- （Santa Cruz de Tenerife）、市名最長 26 字（San Cristóbal de La Laguna），舊上限會把地名截半。
-- 欄位本身在資料庫是 text、沒有長度限制，這裡不需要改型別，只補 country 欄與註解。
-- 沿用既有 persons RLS（persons_account_member_all），不另立新政策。
-- Run after 027_localized_notification_copy.sql.

begin;

alter table public.persons
  add column if not exists country text;

alter table public.persons
  drop constraint if exists persons_country_iso2;
alter table public.persons
  add constraint persons_country_iso2
  check (country is null or country ~ '^[A-Z]{2}$');

comment on column public.persons.country is
  'ISO 3166-1 alpha-2 國別（TW/JP/ES/US/GB…）。決定個人資料「所在地」用哪一國的行政區清單；空值＝沿用台灣行為。';
comment on column public.persons.county is
  '一級行政區：台灣縣市／日本都道府県／西班牙省／美國州／英國地區。最長以應用層 60 字為準。';
comment on column public.persons.district is
  '二級行政區：台灣區／日本市区町村／西班牙市／美英城市。清單外由使用者自行輸入。';

commit;
