// 035（2026-11-26）：分鐘各帳號各扣＋免費改成「註冊送一次 5 分鐘」。在拋棄式 PostgreSQL（PGlite）上實際呼叫驗證。
// 假資料、不連任何資料庫。模擬正式線的順序：先跑到 034（共用開著、有人已經領過每日／每週免費、
// 有人扣過圈主、有 11/20 以前領過一次性 5 點的老帳號），再套 035。最後另外從 001 跑到 035 全套。
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
  gmaAcct: U(31), gmaUser: U(32), gmaPerson: U(33), gmaGroup: U(34),
  newAcct: U(41), newUser: U(42), newPerson: U(43), newGroup: U(44),
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
await account(ids.momAcct, ids.momUser, ids.momPerson, ids.momGroup, "30 days", "mom");   // 034：每週
await account(ids.dadAcct, ids.dadUser, ids.dadPerson, ids.dadGroup, "2 hours", "dad");   // 034：每天
await account(ids.gmaAcct, ids.gmaUser, ids.gmaPerson, ids.gmaGroup, "120 days", "gma"); // 11/20 以前領過一次性 5 點
await q(`insert into public.subscription_ledger(account_id, provider, status, active_plan, expires_at)
         values ($1, 'apple', 'active', 'plus', now() + interval '20 days')`, [ids.kidAcct]);
await q(`insert into public.credit_wallets(account_id, person_id, wallet_type, period, balance, expires_at)
         values ($1, $2, 'included_monthly', '2026-11-01T00:00Z/2026-12-01T00:00Z', 100, now() + interval '20 days')`,
  [ids.kidAcct, ids.kidPerson]);
for (const p of [ids.momPerson, ids.dadPerson]) {
  await q(`insert into public.family_memberships(account_id, family_group_id, person_id, role)
           values ($1, $2, $3, 'family_contact')`, [ids.kidAcct, ids.kidGroup, p]);
}
// 奶奶：012 那時候送的 5 點（交易鍵 free-signup-trial:<帳號>、放在購買錢包），用掉 3 剩 2
const gmaWallet = await one(`insert into public.credit_wallets(account_id, wallet_type, balance, metadata)
  values ($1, 'purchased', 2, '{"scope":"account","purpose":"signup_trial"}'::jsonb) returning id`, [ids.gmaAcct]);
await q(`insert into public.credit_transactions(account_id, wallet_id, transaction_type, source, amount, balance_after, provider, idempotency_key, reason)
         values ($1, $2, 'grant', 'promo', 5, 5, 'munea_signup', $3, 'free_signup_voice_avatar_trial')`,
  [ids.gmaAcct, gmaWallet.id, `free-signup-trial:${ids.gmaAcct}`]);
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
const status = async (acct, person) => (await one(`select public.munea_credit_share_status($1, $2) as s`, [acct, person])).s;
const grants = async (acct) => (await q(`select idempotency_key from public.credit_transactions where account_id=$1 and transaction_type='grant'`, [acct])).map((r) => r.idempotency_key);

// ── 0. 套 035 之前（034）：媽媽打 12 分鐘（每週 10＋扣子女 2）；爸爸領到今天的 10、用 3 ──
let r = await dial(ids.momUser, ids.momPerson, "mom-before");
let errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 12);
let kid = await balances(ids.kidAcct);
check("前提（034）：媽媽 12 分鐘裡 2 分鐘扣到子女（100→98）", errs.length === 0 && kid.included_monthly === 98, { errs, kid });
await hangup(r.call_id, ids.momUser, "rel-mom-before");
r = await dial(ids.dadUser, ids.dadPerson, "dad-before");
errs = await minutes(r.call_id, ids.dadAcct, ids.dadPerson, 1, 3);
await hangup(r.call_id, ids.dadUser, "rel-dad-before");
check("前提（034）：爸爸今天的每日錢包剩 7", (await balances(ids.dadAcct)).free_allowance === 7, await balances(ids.dadAcct));

// ── 1. 套 035 ──
const sql035 = fs.readFileSync(path.join(repo, "supabase/sql/035_per_account_minutes.sql"), "utf8");
let applied = "ok";
try { await db.exec(sql035); } catch (e) { applied = e.message; try { await db.exec("rollback;"); } catch (_) {} }
check("035 套在 034 上面不報錯", applied === "ok", applied);
const openPeriodic = Number((await one(`select count(*) as c from public.credit_wallets where wallet_type='free_allowance'
  and (period like 'free-daily:%' or period like 'free-weekly:%') and (expires_at is null or expires_at > now())`)).c);
check("每日／每週免費錢包全部收掉（爸爸剩的 7 也收）", openPeriodic === 0, openPeriodic);
const closedRows = Number((await one(`select count(*) as c from public.credit_wallets where metadata->>'closedBy'='035_free_once'`)).c);
check("收掉的錢包資料列保留、標記 closedBy", closedRows === 2, closedRows);

// ── 2. 爸爸（成員、只領過每日、沒領過一次性 5）：補一次 5 分鐘，用完就停，子女不動 ──
let s = await status(ids.dadAcct, ids.dadPerson);
check("爸爸狀態：{mode:free_once, grant:5, remaining:5}、沒有 familyShare", s.allowance.mode === "free_once" && Number(s.allowance.grant) === 5
  && Number(s.allowance.remaining) === 5 && s.familyShare === null && Number(s.sharedSpendable) === 0 && Object.keys(s.allowance).length === 3, s);
r = await dial(ids.dadUser, ids.dadPerson, "dad-after");
errs = await minutes(r.call_id, ids.dadAcct, ids.dadPerson, 1, 6);
kid = await balances(ids.kidAcct);
check("爸爸 5 分鐘扣自己的一次性免費、第 6 分鐘不夠、子女還是 98", errs.length === 1 && errs[0][0] === 6 && kid.included_monthly === 98, { errs, kid });
await hangup(r.call_id, ids.dadUser, "rel-dad-after");
s = await status(ids.dadAcct, ids.dadPerson);
check("爸爸用完：remaining 0、不回補", Number(s.allowance.remaining) === 0 && Number(s.allowance.grant) === 5, s.allowance);
r = await dial(ids.dadUser, ids.dadPerson, "dad-after-2");
check("爸爸沒分鐘：按撥通被拒（圈主有付費也不幫付）", r.status === "reject" && r.reason === "insufficient_credits", r);
check("爸爸只有一筆一次性發點", (await grants(ids.dadAcct)).filter((k) => k === `free-signup-trial:${ids.dadAcct}`).length === 1, await grants(ids.dadAcct));

// ── 3. 媽媽（成員、領過每週、沒領過一次性 5）：一樣補一次 5 ──
r = await dial(ids.momUser, ids.momPerson, "mom-after");
check("媽媽按撥通：補到 5 分鐘、配到座位", r.status === "connect", r);
errs = await minutes(r.call_id, ids.momAcct, ids.momPerson, 1, 6);
kid = await balances(ids.kidAcct);
check("媽媽扣自己的 5、第 6 分鐘不夠、子女還是 98", errs.length === 1 && kid.included_monthly === 98, { errs, kid });
await hangup(r.call_id, ids.momUser, "rel-mom-after");

// ── 4. 奶奶（11/20 以前領過一次性 5、剩 2）：不再發 ──
s = await status(ids.gmaAcct, ids.gmaPerson);
check("奶奶狀態：grant 5、remaining 2（舊的 5 點剩下的）", s.allowance.mode === "free_once" && Number(s.allowance.grant) === 5 && Number(s.allowance.remaining) === 2, s.allowance);
check("奶奶沒有拿到新的 free-once 錢包", (await balances(ids.gmaAcct)).free_allowance === undefined && (await balances(ids.gmaAcct)).purchased === 2, await balances(ids.gmaAcct));

// ── 5. 035 之後註冊的新帳號：查餘額就領到 5；過了幾天也不會再給 ──
await account(ids.newAcct, ids.newUser, ids.newPerson, ids.newGroup, "1 minute", "new");
s = await status(ids.newAcct, ids.newPerson);
check("新帳號：{free_once, 5, 5}", s.allowance.mode === "free_once" && Number(s.allowance.grant) === 5 && Number(s.allowance.remaining) === 5, s.allowance);
const once = await one(`select period, expires_at, balance from public.credit_wallets where account_id=$1 and wallet_type='free_allowance'`, [ids.newAcct]);
check("新帳號錢包：period free-once、不會到期", once.period === "free-once" && once.expires_at === null && Number(once.balance) === 5, once);
const legacyEntry = (await one(`select public.munea_grant_free_signup_trial($1, null) as r`, [ids.newAcct])).r;
check("舊的註冊送點入口：冪等、不會再送", legacyEntry.idempotentReplay === true, legacyEntry);
await q(`update public.accounts set created_at = now() - interval '10 days' where id = $1`, [ids.newAcct]);
await q(`select public.munea_ensure_free_allowance($1)`, [ids.newAcct]);
check("帳號過了 10 天：還是只有那一次 5 分鐘（沒有每天／每週）", (await grants(ids.newAcct)).length === 1 && (await balances(ids.newAcct)).free_allowance === 5, await grants(ids.newAcct));
const win = (await one(`select public.munea_free_allowance_window($1, now()) as w`, [ids.newAcct])).w;
check("免費額度樣子：free_once、5、不到期", win.mode === "free_once" && Number(win.amount) === 5 && win.expiresAt === null, win);

// ── 6. 子女（圈主、付費）：扣自己的月額度、不發一次性免費 ──
r = await dial(ids.kidUser, ids.kidPerson, "kid-1");
errs = await minutes(r.call_id, ids.kidAcct, ids.kidPerson, 1, 2);
kid = await balances(ids.kidAcct);
check("子女自己打扣自己（98→96）、沒有免費錢包", errs.length === 0 && kid.included_monthly === 96 && !("free_allowance" in kid), kid);
await hangup(r.call_id, ids.kidUser, "rel-kid-1");
s = await status(ids.kidAcct, ids.kidPerson);
check("子女狀態：{mode:plan, plan:plus, resetsAt}、沒有 familyShare", s.allowance.mode === "plan" && s.allowance.plan === "plus"
  && !!s.allowance.resetsAt && s.familyShare === null, s);
check("munea_family_share_owner 一律回 null", (await one(`select public.munea_family_share_owner($1, $2) as s`, [ids.momAcct, ids.momPerson])).s === null);

// ── 7. 重跑、方案說明、權限、歷史 ──
let rerun = "ok";
try { await db.exec(sql035); } catch (e) { rerun = e.message; }
check("035 整份重跑不報錯", rerun === "ok", rerun);
const onceGrants = Number((await one(`select count(*) as c from public.credit_transactions where idempotency_key like 'free-signup-trial:%'`)).c);
check("重跑後一次性發點沒變多（爸、媽、奶奶、新帳號各 1）", onceGrants === 4, onceGrants);
const policy = await q(`select version, policy->'free'->>'freeOnceMinutes' as once, policy->'free'->>'signupTrialCredits' as signup,
  policy->'free' ? 'freeTrialDays' as days, policy->'plus'->>'familySharedMinutes' as plus, policy->'pro'->>'familySharedMinutes' as pro
  from public.entitlement_policy_versions where policy_key='munea_app_store_v1' and active`);
check("方案說明 v6 唯一生效：註冊送一次 5、沒有天數、不共用", policy.length === 1 && policy[0].version === 6 && policy[0].once === "5"
  && policy[0].signup === "5" && policy[0].days === false && policy[0].plus === "false" && policy[0].pro === "false", policy);
const exposed = await q(`select routine_name, grantee from information_schema.routine_privileges
  where routine_name in ('munea_credit_share_status','munea_family_share_owner','munea_ensure_free_allowance',
    'munea_free_allowance_window','munea_free_once_received','munea_free_once_remaining') and grantee in ('anon','authenticated','PUBLIC')`);
check("函式沒開給 anon／authenticated／public", exposed.length === 0, exposed);
const history = Number((await one(`select count(*) as c from public.credit_transactions where account_id=$1 and transaction_type='consume' and person_id=$2`, [ids.kidAcct, ids.momPerson])).c);
check("035 以前扣過子女的歷史交易保留（2 筆）", history === 2, history);

// ── 8. 從 001 跑到 035 全套 ──
const full = await freshDb(false);
const fullBad = expectedMissing(full.results);
check("001→035 全套照清單順序跑得完", fullBad.length === 0 && full.results.some(([f, res]) => f === "035_per_account_minutes.sql" && res === "ok"), fullBad);

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
