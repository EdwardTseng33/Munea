// 035 分鐘改回「每個帳號各扣各的」：在拋棄式 PostgreSQL（PGlite）上實際呼叫驗證。假資料、不連任何資料庫。
// 模擬正式線的順序：先跑到 034（共用開著、已經有人扣過圈主），再套 035，之後每個人只扣自己的。
// 最後另外從 001 跑到 035 全套，確認整份清單照順序跑得完。
// 跑法：npm install --no-save @electric-sql/pglite@0.2.17
//       node scripts/sql_sandbox/check_035_per_account_minutes.mjs
import fs from "node:fs";
import path from "node:path";
import { freshDb, repo } from "./migrate.mjs";

let failures = 0;
const check = (label, cond, detail) => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${label}${cond ? "" : "  → " + JSON.stringify(detail)}`);
  if (!cond) failures++;
};
const expectedMissing = (results) => results.filter(([f, r]) => r !== "ok" && !/^00[459]_/.test(f));

const { db, results } = await freshDb(false, { upTo: "034" });
check("001→034 跑得完（004／005／009 需要 pgvector，PGlite 本來就跑不了）", expectedMissing(results).length === 0, expectedMissing(results));

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
await q(`insert into public.subscription_ledger(account_id, provider, status, active_plan, expires_at)
         values ($1, 'apple', 'active', 'plus', now() + interval '20 days')`, [ids.kidAcct]);
await q(`insert into public.credit_wallets(account_id, person_id, wallet_type, period, balance, expires_at)
         values ($1, $2, 'included_monthly', '2026-11-01T00:00Z/2026-12-01T00:00Z', 100, now() + interval '20 days')`,
  [ids.kidAcct, ids.kidPerson]);
for (const p of [ids.momPerson, ids.dadPerson]) {
  await q(`insert into public.family_memberships(account_id, family_group_id, person_id, role)
           values ($1, $2, $3, 'family_contact')`, [ids.kidAcct, ids.kidGroup, p]);
}
await q(`insert into public.credit_wallets(account_id, wallet_type, balance) values ($1, 'purchased', 2)`, [ids.momAcct]);
await q(`insert into public.voice_shards(shard_id, url, region, status, capacity) values ('v1', 'wss://voice.invalid', 'tw', 'ready', 50)
         on conflict (shard_id) do update set status='ready', capacity=50, active_leases=0`);

const balances = async (acct) => Object.fromEntries((await q(
  `select wallet_type, sum(balance)::numeric as b from public.credit_wallets where account_id=$1 and status='active'
     and (expires_at is null or expires_at > now()) group by wallet_type`, [acct])).map((r) => [r.wallet_type, Number(r.b)]));
const dial = async (user, person, key) => (await one(`select public.munea_call_request($1, $2, 'nening', $3) as r`, [user, person, key])).r;
async function minutes(callId, acct, person, from, to) {
  const errs = [];
  for (let m = from; m <= to; m++) {
    try { await q(`select public.munea_call_consume_credit($1, $2, $3, $4)`, [callId, acct, person, m]); }
    catch (e) { errs.push([m, e.message]); }
  }
  return errs;
}
const hangup = async (callId, user, tag) => q(`select public.munea_call_release($1, 1, $2, 'completed', $3)`, [callId, tag, user]);

// ── 0. 套 035 之前（034 共用開著）：媽媽打 12 分鐘，超過免費的 2 分鐘扣到子女 ──
let r = await dial(ids.momUser, ids.momPerson, "mom-before");
let errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 12);
let kid = await balances(ids.kidAcct), mom = await balances(ids.momAcct);
check("前提（034）：媽媽 12 分鐘裡有 2 分鐘扣子女（100→98），自己的舊 2 點沒動", errs.length === 0 && kid.included_monthly === 98 && mom.purchased === 2, { errs, kid, mom });
await hangup(r.call_id, ids.momUser, "rel-mom-before");

// ── 1. 套 035 ──
const sql035 = fs.readFileSync(path.join(repo, "supabase/sql/035_per_account_minutes.sql"), "utf8");
let applied = "ok";
try { await db.exec(sql035); } catch (e) { applied = e.message; }
check("035 套在 034 上面不報錯", applied === "ok", applied);

// ── 2. 媽媽（成員、舊帳號、這週免費已用完）：只剩自己的 2 點，扣完就不能撥，子女不動 ──
r = await dial(ids.momUser, ids.momPerson, "mom-after-1");
check("媽媽還有自己的 2 點：配得到座位", r.status === "connect", r);
errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 3);
kid = await balances(ids.kidAcct); mom = await balances(ids.momAcct);
check("媽媽扣自己的 2 點、第 3 分鐘不夠、子女還是 98", errs.length === 1 && /insufficient_credits/.test(errs[0][1])
  && (mom.purchased ?? 0) === 0 && kid.included_monthly === 98, { errs, mom, kid });
await hangup(r.call_id, ids.momUser, "rel-mom-after-1");
r = await dial(ids.momUser, ids.momPerson, "mom-after-2");
check("媽媽自己沒分鐘了：按撥通被拒（圈主有付費也不幫付）", r.status === "reject" && r.reason === "insufficient_credits", r);

// ── 3. 爸爸（成員、新帳號第 1 天）：只有自己今天的 10 分鐘 ──
r = await dial(ids.dadUser, ids.dadPerson, "dad-1");
check("爸爸按撥通：配到座位", r.status === "connect", r);
errs = await minutes(r.call_id, ids.dadAcct, ids.dadPerson, 1, 11);
const dad = await balances(ids.dadAcct);
kid = await balances(ids.kidAcct);
check("爸爸 10 分鐘扣自己今天的免費額度、第 11 分鐘不夠、子女還是 98", errs.length === 1 && errs[0][0] === 11
  && dad.free_allowance === 0 && kid.included_monthly === 98, { errs, dad, kid });
await hangup(r.call_id, ids.dadUser, "rel-dad-1");

// ── 4. 子女（圈主、付費）：扣自己的月額度 ──
r = await dial(ids.kidUser, ids.kidPerson, "kid-1");
errs = await minutes(r.call_id, ids.kidAcct, ids.kidPerson, 1, 2);
kid = await balances(ids.kidAcct);
check("子女自己打扣自己（98→96）、沒有免費錢包", errs.length === 0 && kid.included_monthly === 96 && !("free_allowance" in kid), kid);
await hangup(r.call_id, ids.kidUser, "rel-kid-1");

// ── 5. /credits/balance 狀態：沒有 familyShare ──
const kidStatus = (await one(`select public.munea_credit_share_status($1, $2) as s`, [ids.kidAcct, ids.kidPerson])).s;
check("圈主狀態：familyShare=null、sharedSpendable=0", kidStatus.familyShare === null && Number(kidStatus.sharedSpendable) === 0, kidStatus);
check("圈主狀態：mode=plan、plan=plus、resetsAt 讀自己月額度的到期日", kidStatus.allowance.mode === "plan" && kidStatus.allowance.plan === "plus"
  && !!kidStatus.allowance.resetsAt, kidStatus.allowance);
const momStatus = (await one(`select public.munea_credit_share_status($1, $2) as s`, [ids.momAcct, ids.momPerson])).s;
check("成員狀態：familyShare=null、sharedSpendable=0（不再把圈主的分鐘算給她）", momStatus.familyShare === null && Number(momStatus.sharedSpendable) === 0, momStatus);
check("成員狀態：免費規則照舊（每週、本週剩 0）", momStatus.allowance.mode === "free_weekly" && Number(momStatus.allowance.weekGrant) === 10
  && Number(momStatus.allowance.weekRemaining) === 0, momStatus.allowance);
const dadStatus = (await one(`select public.munea_credit_share_status($1, $2) as s`, [ids.dadAcct, ids.dadPerson])).s;
check("新成員狀態：每天模式第 1 天、今天 10 分鐘", dadStatus.allowance.mode === "free_daily" && dadStatus.allowance.trialDay === 1
  && Number(dadStatus.allowance.todayGrant) === 10, dadStatus.allowance);
check("munea_family_share_owner 一律回 null", (await one(`select public.munea_family_share_owner($1, $2) as s`, [ids.momAcct, ids.momPerson])).s === null);

// ── 6. 免費規則沒被動到：第 1／7／8 天、週一 ──
await q(`update public.accounts set created_at = ('2026-11-10 10:00'::timestamp at time zone 'Asia/Taipei') where id = $1`, [ids.dadAcct]);
const w = async (at) => (await one(`select public.munea_free_allowance_window($1, ($2::timestamp at time zone 'Asia/Taipei')) as w`, [ids.dadAcct, at])).w;
let x = await w("2026-11-10 23:59");
check("第 1 天：每天 10 分鐘", x.mode === "free_daily" && x.trialDay === 1 && Number(x.amount) === 10, x);
x = await w("2026-11-16 23:59");
check("第 7 天還是每天", x.mode === "free_daily" && x.trialDay === 7, x);
x = await w("2026-11-17 00:00");
check("第 8 天換每週 10 分鐘", x.mode === "free_weekly" && Number(x.amount) === 10, x);

// ── 7. 重跑、方案說明、權限 ──
let rerun = "ok";
try { await db.exec(sql035); } catch (e) { rerun = e.message; }
check("035 整份重跑不報錯", rerun === "ok", rerun);
const policy = await q(`select version, policy->'plus'->>'familySharedMinutes' as plus, policy->'pro'->>'familySharedMinutes' as pro
  from public.entitlement_policy_versions where policy_key='munea_app_store_v1' and active`);
check("方案說明 v6 是唯一生效版、Plus／Pro 都不共用", policy.length === 1 && policy[0].version === 6 && policy[0].plus === "false" && policy[0].pro === "false", policy);
const grants = await q(`select grantee, privilege_type from information_schema.routine_privileges
  where routine_name in ('munea_credit_share_status','munea_family_share_owner') and grantee in ('anon','authenticated','PUBLIC')`);
check("函式沒開給 anon／authenticated／public", grants.length === 0, grants);
const history = Number((await one(`select count(*) as c from public.credit_transactions where account_id=$1 and transaction_type='consume' and person_id=$2`, [ids.kidAcct, ids.momPerson])).c);
check("035 以前扣過子女的歷史交易保留（2 筆）", history === 2, history);

// ── 8. 從 001 跑到 035 全套 ──
const full = await freshDb(false);
const fullBad = expectedMissing(full.results);
check("001→035 全套照清單順序跑得完", fullBad.length === 0 && full.results.some(([f, r]) => f === "035_per_account_minutes.sql" && r === "ok"), fullBad);

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
