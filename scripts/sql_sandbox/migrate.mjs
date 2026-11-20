// 拋棄式資料庫：在記憶體裡開一個 PostgreSQL 16（PGlite，WASM 版、不裝系統服務、不連任何雲端），
// 照 supabase/migration-manifest.json 的順序把 supabase/sql 全部跑一遍。
// 只給本機驗證 SQL 用；需要先 `npm install --no-save @electric-sql/pglite@0.2.17`。
// 004／005／009 需要 pgvector（PGlite 沒有），跑不起來是預期的，跟計費無關。
import { PGlite } from "@electric-sql/pglite";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const repo = process.env.MUNEA_REPO || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const only = null;
const manifest = JSON.parse(fs.readFileSync(path.join(repo, "supabase/migration-manifest.json"), "utf8"));

export async function freshDb(log = true) {
  const db = new PGlite();
  await db.exec(`
    create schema if not exists auth;
    create table auth.users (id uuid primary key, email text, raw_user_meta_data jsonb default '{}'::jsonb,
      created_at timestamptz default now(), last_sign_in_at timestamptz);
    create or replace function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
    create or replace function auth.jwt() returns jsonb language sql stable as $$ select '{}'::jsonb $$;
    create or replace function auth.role() returns text language sql stable as $$ select 'service_role'::text $$;
    do $$ begin
      if not exists (select 1 from pg_roles where rolname='anon') then create role anon; end if;
      if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
      if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role; end if;
    end $$;
  `);
  const results = [];
  for (const m of manifest.migrations) {
    if (only && !only.has(m.identity)) continue;
    let sql = fs.readFileSync(path.join(repo, "supabase/sql", m.filename), "utf8");
    sql = sql.replace(/create extension if not exists pgcrypto;/gi, "-- pgcrypto: gen_random_uuid is core");
    try {
      await db.exec(sql);
      results.push([m.filename, "ok"]);
    } catch (e) {
      results.push([m.filename, "FAIL: " + String(e.message).slice(0, 200)]);
      try { await db.exec("rollback;"); } catch (_) {}
    }
  }
  if (log) for (const [f, r] of results) console.log(r === "ok" ? "  ok  " : "  !!  ", f, r === "ok" ? "" : r);
  return { db, results };
}
