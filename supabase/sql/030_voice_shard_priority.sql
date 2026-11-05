-- 2026-11-05 Edward 拍板 B「平常走快線、人多才分流」：語音座位加「優先序」。
--
-- 背景：11/5 壓測——現行 Gemini 開發者通道每分鐘用量上限 100 萬，50 人同時開會一起斷線；
-- Google 雲端通道（Vertex，2.5 模型）50 人全通但她開口慢約 2 秒。所以平常都走快線，
-- 快線滿了（名額）才把新來的人分到雲端備援線。
--
-- 這支只改 munea_call_request 挑語音座位的排序：先比 metadata.priority（沒填＝0＝快線），
-- 同優先序才照原本「先塞滿最忙的」。函式介面、權限、其他邏輯一字不動（從 010 原樣複製）。
-- 備援線那一列（priority=10）等雲端備援服務開好後另外登記；沒登記前這支跟原本行為完全一樣。
--
-- 回滾：重新貼 010_realtime_call_control.sql 裡的 munea_call_request 那一段即可。

create or replace function public.munea_call_request(
  p_user_id uuid,
  p_person_id uuid,
  p_character_id text,
  p_idempotency_key text,
  p_queue_max integer default 30
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_account_id uuid;
  v_lease public.call_leases%rowtype;
  v_queue public.call_queue%rowtype;
  v_worker public.gpu_workers%rowtype;
  v_voice public.voice_shards%rowtype;
  v_slot integer;
  v_available numeric;
  v_holds numeric;
  v_position integer;
  v_depth integer;
  v_call_id uuid;
begin
  if coalesce(trim(p_idempotency_key), '') = '' then
    return pg_catalog.jsonb_build_object('status','reject','reason','idempotency_key_required');
  end if;
  perform pg_catalog.pg_advisory_xact_lock(724338221);
  perform public.munea_call_reap_expired();

  select am.account_id into v_account_id
  from public.account_members am
  where am.user_id = p_user_id and am.status = 'active'
  order by case am.role when 'owner' then 0 when 'admin' then 1 else 2 end
  limit 1;
  if v_account_id is null then
    return pg_catalog.jsonb_build_object('status','reject','reason','account_not_ready');
  end if;
  if p_person_id is not null and not exists (
    select 1 from public.persons p where p.id = p_person_id and p.account_id = v_account_id and p.deleted_at is null
  ) then
    return pg_catalog.jsonb_build_object('status','reject','reason','person_not_owned');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_account_id::text, 724338221)
  );

  select * into v_lease from public.call_leases
  where account_id = v_account_id and idempotency_key = p_idempotency_key
    and state in ('reserved','connecting','active','ending')
  limit 1;
  if found then
    return pg_catalog.jsonb_build_object(
      'status','connect','call_id',v_lease.call_id,'lease_version',v_lease.lease_version,
      'slot_id',v_lease.slot_id,'state',v_lease.state,
      'worker',(select pg_catalog.jsonb_build_object('worker_id',w.worker_id,'url',w.url) from public.gpu_workers w where w.worker_id=v_lease.worker_id),
      'voice',(select pg_catalog.jsonb_build_object('shard_id',s.shard_id,'url',s.url) from public.voice_shards s where s.shard_id=v_lease.voice_shard_id)
    );
  end if;

  select * into v_queue from public.call_queue
  where account_id = v_account_id and idempotency_key = p_idempotency_key and state = 'queued'
  limit 1;
  if found then
    update public.call_queue set last_heartbeat_at = now() where call_id = v_queue.call_id;
    select count(*)::integer into v_position from public.call_queue
      where state='queued' and enqueued_at <= v_queue.enqueued_at;
    if v_position > 1 then
      select count(*)::integer into v_depth from public.call_queue where state='queued';
      return pg_catalog.jsonb_build_object('status','queued','call_id',v_queue.call_id,
        'queue',pg_catalog.jsonb_build_object('position',v_position,'depth',v_depth,'eta_s',v_position*120));
    end if;
  end if;

  perform 1 from public.credit_wallets
  where account_id=v_account_id and status='active' and balance>0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id=p_person_id)
  order by id
  for update;
  select coalesce(sum(balance),0) into v_available from public.credit_wallets
  where account_id=v_account_id and status='active' and balance>0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id=p_person_id);
  select coalesce(sum(amount),0) into v_holds from public.call_credit_holds
  where account_id=v_account_id and state='held';
  if v_available - v_holds < 1 then
    if v_queue.call_id is not null then update public.call_queue set state='cancelled' where call_id=v_queue.call_id; end if;
    return pg_catalog.jsonb_build_object('status','reject','reason','insufficient_credits');
  end if;

  select * into v_voice from public.voice_shards
  where status='ready' and active_leases < capacity
  -- 030：先排「優先序」小的（快線＝預設 0；分流備援線 metadata.priority=10），同優先序才照原本「先塞滿最忙的」。
  -- 原本只看忙碌比例：尖峰過後快線空了、備援線還有幾通在講，新來的人會一直被分到比較慢的備援線。
  order by coalesce(nullif(metadata->>'priority','')::integer, 0), active_leases::numeric/capacity desc, shard_id
  for update skip locked limit 1;
  select * into v_worker from public.gpu_workers
  where status='ready' and active_leases < capacity
  order by active_leases::numeric/capacity desc, worker_id
  for update skip locked limit 1;

  if v_voice.shard_id is not null and v_worker.worker_id is not null then
    select s into v_slot from pg_catalog.generate_series(1,v_worker.capacity) s
    where not exists (
      select 1 from public.call_leases l where l.worker_id=v_worker.worker_id and l.slot_id=s
        and l.state in ('reserved','connecting','active','ending')
    ) order by s limit 1;
    if v_slot is not null then
      v_call_id := coalesce(v_queue.call_id, gen_random_uuid());
      if v_queue.call_id is not null then
        update public.call_queue set state='promoted' where call_id=v_queue.call_id;
      end if;
      insert into public.call_leases (
        call_id,account_id,person_id,user_id,character_id,state,voice_shard_id,worker_id,
        slot_id,lease_version,idempotency_key,lease_expires_at,last_heartbeat_at
      ) values (
        v_call_id,v_account_id,p_person_id,p_user_id,p_character_id,'reserved',v_voice.shard_id,
        v_worker.worker_id,v_slot,1,p_idempotency_key,now()+interval '60 seconds',now()
      );
      update public.voice_shards set active_leases=active_leases+1,updated_at=now() where shard_id=v_voice.shard_id;
      update public.gpu_workers set active_leases=active_leases+1,idle_since=null,updated_at=now() where worker_id=v_worker.worker_id;
      insert into public.call_credit_holds(call_id,account_id,amount) values(v_call_id,v_account_id,1);
      return pg_catalog.jsonb_build_object(
        'status','connect','call_id',v_call_id,'lease_version',1,'slot_id',v_slot,'state','reserved',
        'worker',pg_catalog.jsonb_build_object('worker_id',v_worker.worker_id,'url',v_worker.url),
        'voice',pg_catalog.jsonb_build_object('shard_id',v_voice.shard_id,'url',v_voice.url)
      );
    end if;
  end if;

  if v_queue.call_id is null then
    select count(*)::integer into v_depth from public.call_queue where state='queued';
    if v_depth >= greatest(1,least(p_queue_max,30)) then
      return pg_catalog.jsonb_build_object('status','reject','reason','queue_full');
    end if;
    insert into public.call_queue(account_id,person_id,user_id,character_id,idempotency_key)
      values(v_account_id,p_person_id,p_user_id,p_character_id,p_idempotency_key)
      returning * into v_queue;
  end if;
  select count(*)::integer into v_position from public.call_queue
    where state='queued' and enqueued_at <= v_queue.enqueued_at;
  select count(*)::integer into v_depth from public.call_queue where state='queued';
  return pg_catalog.jsonb_build_object('status','queued','call_id',v_queue.call_id,
    'queue',pg_catalog.jsonb_build_object('position',v_position,'depth',v_depth,'eta_s',v_position*120));
end;
$$;
