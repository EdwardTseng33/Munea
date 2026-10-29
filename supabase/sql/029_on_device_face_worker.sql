-- 2026-10-29 Edward 拍板「臉在手機上跑、聲音在雲端」。
--
-- 背景：總機（munea_call_request）配對一通電話要同時有「聲音座位」（voice_shards）和
-- 「臉的座位」（gpu_workers）。雲端顯示卡 9/6 起全部 terminated，於是每通電話都永遠排隊、
-- 打不通（10/14 唯一一通排隊 7.8 秒被取消；最後一通成功是 8/13）。
--
-- 新方法：寧寧／沐沐是手機上的插圖（web/src/companion-face.js），不需要雲端顯示卡。
-- 把「臉的座位」登記成手機自己畫：url = phone://on-device-face、名額 500、不計費。
-- App（web/src/app.js getAvatarUrl）看到 phone:// 就不接雲端臉、聲音走本機播放、插圖跟著聲音動。
--
-- 不改任何函式、不動表結構（擬真人臉的配對程式停用不刪：顯示卡若重新上線、照原本規則一起排）。
-- 回滾：update public.gpu_workers set status='terminated' where worker_id='on-device-face';
--
-- 另：voice_shards 的 active_leases 帳面卡在 3（7 月以來沒有任何進行中的通話＝漏扣），歸零；
-- 名額照 2026-07-24「上線併發 8-10」拍板調成 10。

insert into public.gpu_workers (
  worker_id, url, region, provider, status, capacity, active_leases,
  last_heartbeat_at, ready_at, hourly_cost, metadata
) values (
  'on-device-face', 'phone://on-device-face', 'device', 'on-device', 'ready', 500, 0,
  now(), now(), 0,
  '{"kind":"on_device_face","note":"2026-10-29 臉在手機上跑（companion-face.js），不需要雲端顯示卡"}'::jsonb
)
on conflict (worker_id) do update set
  url = excluded.url, region = excluded.region, provider = excluded.provider,
  status = 'ready', capacity = excluded.capacity, hourly_cost = 0,
  metadata = excluded.metadata, updated_at = now();

update public.voice_shards
  set active_leases = 0, capacity = 10, updated_at = now()
  where shard_id = 'gemini-live-asia-east1-01'
    and not exists (
      select 1 from public.call_leases
      where state in ('reserved','connecting','active','ending')
    );
