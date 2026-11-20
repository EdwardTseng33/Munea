// 034 家人圈共用分鐘＋每日／每週免費額度：在拋棄式 PostgreSQL（PGlite）上實際呼叫
// munea_call_request／munea_call_consume_credit 驗證。假資料、不連任何資料庫。
// 跑法：npm install --no-save @electric-sql/pglite@0.2.17
//       node scripts/sql_sandbox/check_034_family_shared_minutes.mjs
import fs from "node:fs";
import path from "node:path";
import { freshDb, repo } from "./migrate.mjs";

const { db, results } = await freshDb(false);
const bad = results.filter(([f, r]) => r !== "ok" && !/^00[459]_/.test(f));
if (bad.length) { console.log("unexpected migration failures", bad); process.exit(1); }

let failures = 0;
const check = (label, cond, detail) => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${label}${cond ? "" : "  → " + JSON.stringify(detail)}`);
  if (!cond) failures++;
};
const q = async (sql, params = []) => (await db.query(sql, params)).rows;
const one = async (sql, params = []) => (await q(sql, params))[0];

const U = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ids = {
  kidAcct: U(1), kidUser: U(2), kidPerson: U(3), kidGroup: U(4),
  momAcct: U(11), momUser: U(12), momPerson: U(13), momGroup: U(14),
  dadAcct: U(21), dadUser: U(22), dadPerson: U(23), dadGroup: U(24),
};

async function account(acct, user, person, group, createdAgo, label) {
  await q(`insert into auth.users(id, email) values ($1, $2)`, [user, `${label}@example.invalid`]);
  await q(`insert into public.accounts(id, name, created_at) values ($1, $2, now() - $3::interval)`, [acct, label, createdAgo]);
  await q(`insert into public.account_members(account_id, user_id, role, status) values ($1, $2, 'owner', 'active')`, [acct, user]);
  await q(`insert into public.persons(id, account_id, display_name, is_primary_care_recipient) values ($1, $2, $3, true)`, [person, acct, label]);
  await q(`insert into public.family_groups(id, account_id) values ($1, $2)`, [group, acct]);
  await q(`insert into public.family_memberships(account_id, family_group_id, person_id, role, created_at)
           values ($1, $2, $3, 'primary_user', now() - $4::interval)`, [acct, group, person, createdAgo]);
}

await account(ids.kidAcct, ids.kidUser, ids.kidPerson, ids.kidGroup, "60 days", "kid");
await account(ids.momAcct, ids.momUser, ids.momPerson, ids.momGroup, "30 days", "mom");   // 舊帳號 → 每週
await account(ids.dadAcct, ids.dadUser, ids.dadPerson, ids.dadGroup, "2 hours", "dad");   // 新帳號 → 每天
// 子女付 Plus、月額度 100
await q(`insert into public.subscription_ledger(account_id, provider, status, active_plan, expires_at)
         values ($1, 'apple', 'active', 'plus', now() + interval '20 days')`, [ids.kidAcct]);
await q(`insert into public.credit_wallets(account_id, person_id, wallet_type, period, balance, expires_at)
         values ($1, $2, 'included_monthly', '2026-11-01T00:00Z/2026-12-01T00:00Z', 100, now() + interval '20 days')`,
  [ids.kidAcct, ids.kidPerson]);
// 爸媽被邀進子女的圈
for (const p of [ids.momPerson, ids.dadPerson]) {
  await q(`insert into public.family_memberships(account_id, family_group_id, person_id, role)
           values ($1, $2, $3, 'family_contact')`, [ids.kidAcct, ids.kidGroup, p]);
}
// 媽媽還有舊的一次性 5 點剩 2
await q(`insert into public.credit_wallets(account_id, wallet_type, balance) values ($1, 'purchased', 2)`, [ids.momAcct]);
// 聲音座位
await q(`insert into public.voice_shards(shard_id, url, region, status, capacity) values ('v1', 'wss://voice.invalid', 'tw', 'ready', 50)
         on conflict (shard_id) do update set status='ready', capacity=50, active_leases=0`);

const balances = async (acct) => Object.fromEntries((await q(
  `select wallet_type, sum(balance)::numeric as b from public.credit_wallets where account_id=$1 and status='active'
     and (expires_at is null or expires_at > now()) group by wallet_type`, [acct])).map((r) => [r.wallet_type, Number(r.b)]));

async function dial(user, person, key) {
  return (await one(`select public.munea_call_request($1, $2, 'nening', $3) as r`, [user, person, key])).r;
}
async function minutes(callId, acct, person, from, to) {
  const errs = [];
  for (let m = from; m <= to; m++) {
    try { await q(`select public.munea_call_consume_credit($1, $2, $3, $4)`, [callId, acct, person, m]); }
    catch (e) { errs.push([m, e.message]); }
  }
  return errs;
}

// ── 1. 媽媽（成員、舊帳號）：先扣自己這週 10 分鐘，再扣子女，最後才扣自己的舊 5 點 ──
let r = await dial(ids.momUser, ids.momPerson, "mom-1");
check("成員按撥通：配到座位", r.status === "connect", r);
let errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 13);
check("成員 13 分鐘都扣得到", errs.length === 0, errs);
let mom = await balances(ids.momAcct), kid = await balances(ids.kidAcct);
check("媽媽這週免費 10 分鐘用完（free_allowance=0）", (mom.free_allowance ?? 0) === 0, mom);
check("子女月額度 100→97（超過免費的 3 分鐘扣子女）", kid.included_monthly === 97, kid);
check("媽媽舊的一次性點數沒先被扣（還是 2）", mom.purchased === 2, mom);
const week = await one(`select period, metadata->>'grant' as g from public.credit_wallets where account_id=$1 and wallet_type='free_allowance'`, [ids.momAcct]);
check("舊帳號直接走每週（週期鍵 free-weekly:週一）", /^free-weekly:\d{4}-\d{2}-\d{2}$/.test(week.period) && week.g === "10", week);
const kidTx = await q(`select person_id, amount, metadata from public.credit_transactions where account_id=$1 and transaction_type='consume'`, [ids.kidAcct]);
check("扣子女的交易記在子女帳上、person_id＝媽媽", kidTx.length === 3 && kidTx.every((t) => t.person_id === ids.momPerson), kidTx);
check("交易 metadata 標來電帳號與共用來源", kidTx.every((t) => t.metadata.callerAccountId === ids.momAcct && t.metadata.sharedFromAccountId === ids.kidAcct), kidTx[0]);
const replay = await minutes(r.call_id, ids.momAcct, ids.momPerson, 13, 13);
check("同一分鐘重送不重複扣", replay.length === 0 && (await balances(ids.kidAcct)).included_monthly === 97, await balances(ids.kidAcct));

// 結束通話（放掉按撥通時的 1 點保留，跟 App 掛斷一樣）
const hangup = async (callId, user, tag) => q(`select public.munea_call_release($1, 1, $2, 'completed', $3)`, [callId, tag, user]);
await hangup(r.call_id, ids.momUser, "rel-mom-1");

// ── 2. 爸爸（新帳號、第 1 天）：每天 10 分鐘先用 ──
r = await dial(ids.dadUser, ids.dadPerson, "dad-1");
check("新成員按撥通：配到座位", r.status === "connect", r);
errs = await minutes(r.call_id, ids.dadAcct, ids.dadPerson, 1, 4);
const dad = await balances(ids.dadAcct);
check("新帳號第 1 天：今天的 10 分鐘先扣（剩 6）、子女不動", errs.length === 0 && dad.free_allowance === 6 && (await balances(ids.kidAcct)).included_monthly === 97, { dad, errs });
const dayWallet = await one(`select period, expires_at from public.credit_wallets where account_id=$1 and wallet_type='free_allowance'`, [ids.dadAcct]);
const taipeiToday = (await one(`select to_char((now() at time zone 'Asia/Taipei')::date, 'YYYY-MM-DD') as d`)).d;
check("每天的錢包：週期鍵是台灣今天、台灣午夜到期", dayWallet.period === `free-daily:${taipeiToday}`
  && (await one(`select ($1::timestamptz at time zone 'Asia/Taipei')::time = '00:00' as ok`, [dayWallet.expires_at])).ok, dayWallet);

await hangup(r.call_id, ids.dadUser, "rel-dad-1");

// ── 3. 子女自己打：扣自己的月額度、不發免費額度 ──
r = await dial(ids.kidUser, ids.kidPerson, "kid-1");
errs = await minutes(r.call_id, ids.kidAcct, ids.kidPerson, 1, 2);
kid = await balances(ids.kidAcct);
check("圈主自己打扣自己（97→95）、沒有免費錢包", errs.length === 0 && kid.included_monthly === 95 && !("free_allowance" in kid), kid);
await hangup(r.call_id, ids.kidUser, "rel-kid-1");

// ── 4. 狀態：圈主看整圈、成員只看自己 ──
const ownerStatus = (await one(`select public.munea_credit_share_status($1, $2) as s`, [ids.kidAcct, ids.kidPerson])).s;
const usage = Object.fromEntries(ownerStatus.familyShare.usage.map((u) => [u.personId, Number(u.minutes)]));
check("圈主狀態：role=owner、plan=plus、mode=plan", ownerStatus.familyShare.role === "owner" && ownerStatus.familyShare.plan === "plus" && ownerStatus.allowance.mode === "plan", ownerStatus);
check("圈主看得到每個人：媽媽 3、自己 2", usage[ids.momPerson] === 3 && usage[ids.kidPerson] === 2 && Object.keys(usage).length === 2, usage);
check("圈主狀態：本月剩 95、發 100（沒有發點交易時用方案預設）", Number(ownerStatus.familyShare.monthRemaining) === 95 && Number(ownerStatus.familyShare.monthGrant) === 100, ownerStatus.familyShare);
const memberStatus = (await one(`select public.munea_credit_share_status($1, $2) as s`, [ids.momAcct, ids.momPerson])).s;
check("成員狀態：role=member、只看到自己那列", memberStatus.familyShare.role === "member"
  && memberStatus.familyShare.usage.length === 1 && memberStatus.familyShare.usage[0].personId === ids.momPerson, memberStatus.familyShare);
check("成員狀態：每週模式、本週剩 0、可共用 95", memberStatus.allowance.mode === "free_weekly" && Number(memberStatus.allowance.weekRemaining) === 0
  && Number(memberStatus.sharedSpendable) === 95, memberStatus);

// ── 5. 圈主沒付費：成員扣自己的，扣完就不能撥 ──
await q(`update public.subscription_ledger set status='expired', updated_at=now() where account_id=$1`, [ids.kidAcct]);
r = await dial(ids.momUser, ids.momPerson, "mom-2");
check("圈主過期後成員還有自己的 2 點：配得到座位", r.status === "connect", r);
errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 3);
mom = await balances(ids.momAcct); kid = await balances(ids.kidAcct);
check("圈主沒付費：扣媽媽自己的 2 點、第 3 分鐘不夠、子女一點都沒動", errs.length === 1 && /insufficient_credits/.test(errs[0][1])
  && (mom.purchased ?? 0) === 0 && kid.included_monthly === 95, { errs, mom, kid });
await hangup(r.call_id, ids.momUser, "rel-mom-2");
r = await dial(ids.momUser, ids.momPerson, "mom-3");
check("沒點數又沒人共用：按撥通被拒（insufficient_credits）", r.status === "reject" && r.reason === "insufficient_credits", r);
await q(`update public.subscription_ledger set status='active', updated_at=now() where account_id=$1`, [ids.kidAcct]);
r = await dial(ids.momUser, ids.momPerson, "mom-4");
check("圈主恢復付費：成員又撥得出去", r.status === "connect", r);

// ── 6. 第 1／7／8 天、週一、護欄 ──
await q(`update public.accounts set created_at = ('2026-11-10 10:00'::timestamp at time zone 'Asia/Taipei') where id = $1`, [ids.dadAcct]);
const w = async (at) => (await one(`select public.munea_free_allowance_window($1, ($2::timestamp at time zone 'Asia/Taipei')) as w`, [ids.dadAcct, at])).w;
let x = await w("2026-11-10 23:59");
check("第 1 天：free_daily、trialDay 1、10 分鐘", x.mode === "free_daily" && x.trialDay === 1 && Number(x.amount) === 10, x);
x = await w("2026-11-11 00:00");
check("台灣午夜跨日：第 2 天、新的週期鍵", x.trialDay === 2 && x.period === "free-daily:2026-11-11", x);
x = await w("2026-11-16 23:59");
check("第 7 天還是每天", x.mode === "free_daily" && x.trialDay === 7, x);
x = await w("2026-11-17 00:00");
check("第 8 天換每週、週期從週一 11/16 起", x.mode === "free_weekly" && x.period === "free-weekly:2026-11-16" && x.trialDay === null, x);
x = await w("2026-11-23 00:00");
check("週一台灣午夜重置", x.period === "free-weekly:2026-11-23", x);
x = await w("2026-11-22 23:59");
check("週日 23:59 還是上週", x.period === "free-weekly:2026-11-16", x);
const used = Number((await one(`select public.munea_free_allowance_month_used() as u`)).u);
check("本月全平台免費消耗算得出來（媽媽 10＋爸爸 4＝14）", used === 14, used);
await q(`update public.free_allowance_settings set monthly_cap_minutes = 14 where id = 1`);
await q(`update public.accounts set created_at = now() - interval '1 hour' where id = $1`, [ids.dadAcct]);
x = (await one(`select public.munea_free_allowance_window($1, now()) as w`, [ids.dadAcct])).w;
check("達到上限：新發的每日額度降成 5", Number(x.amount) === 5 && x.capReached === true, x);
await q(`update public.accounts set created_at = now() - interval '30 days' where id = $1`, [ids.dadAcct]);
x = (await one(`select public.munea_free_allowance_window($1, now()) as w`, [ids.dadAcct])).w;
check("達到上限：每週額度不受影響（10）", Number(x.amount) === 10, x);

// ── 7. 舊入口與重跑 ──
const legacy = (await one(`select public.munea_grant_free_signup_trial($1, null) as r`, [ids.momAcct])).r;
check("舊的註冊送點入口不再送 5 點（回這週的免費額度、冪等）", legacy.idempotentReplay === true && Number(legacy.credits) === 10, legacy);
const sql034 = fs.readFileSync(path.join(repo, "supabase/sql/034_family_shared_minutes_daily_free.sql"), "utf8");
let rerun = "ok";
try { await db.exec(sql034); } catch (e) { rerun = e.message; }
check("034 整份重跑不報錯", rerun === "ok", rerun);
const walletCount = Number((await one(`select count(*) as c from public.credit_wallets where wallet_type='free_allowance'`)).c);
check("重跑後免費錢包沒有變多", walletCount === 2, walletCount);
const policy = await one(`select version from public.entitlement_policy_versions where policy_key='munea_app_store_v1' and active`);
check("方案說明 v5 是唯一生效版", policy.version === 5, policy);
const grants = await q(`select grantee, privilege_type from information_schema.routine_privileges
  where routine_name in ('munea_credit_share_status','munea_ensure_free_allowance','munea_family_share_owner') and grantee in ('anon','authenticated','PUBLIC')`);
check("新函式沒開給 anon／authenticated／public", grants.length === 0, grants);

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
