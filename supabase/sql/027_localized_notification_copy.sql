-- Localize server-generated notification copy from the recipient's App locale.
-- Language selection is independent from country, safety, legal, and data regions.

create or replace function public.notification_locale_for_person(p_person_id uuid)
returns text
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_locale text;
begin
  select pd.locale
    into v_locale
  from public.push_devices pd
  where pd.person_id = p_person_id
    and pd.invalidated_at is null
    and pd.notifications_enabled
  order by pd.last_seen_at desc nulls last
  limit 1;

  if v_locale is null then
    select a.locale
      into v_locale
    from public.persons p
    join public.accounts a on a.id = p.account_id
    where p.id = p_person_id
    limit 1;
  end if;

  return case
    when lower(coalesce(v_locale, 'zh-TW')) like 'en%' then 'en'
    when lower(coalesce(v_locale, 'zh-TW')) like 'ja%' then 'ja'
    when lower(coalesce(v_locale, 'zh-TW')) like 'es%' then 'es'
    else 'zh-TW'
  end;
end;
$$;

revoke all on function public.notification_locale_for_person(uuid) from public, anon, authenticated;
grant execute on function public.notification_locale_for_person(uuid) to service_role;


create or replace function public.notification_copy(
  p_locale text,
  p_key text,
  p_sender_label text default null,
  p_status text default null
)
returns text
language sql
immutable
set search_path = ''
as $$
  select case coalesce(p_locale, 'zh-TW')
    when 'en' then case p_key
      when 'generic_title' then 'Munea Reminder'
      when 'generic_body' then 'Your health reminder is ready. Unlock to view it.'
      when 'family_relay_title' then coalesce(nullif(p_sender_label, ''), 'A family member') || ' sent you a message'
      when 'family_relay_public_body' then 'A family member sent you a message. Unlock to listen.'
      when 'invitation_applied_title' then 'A family member requested to join your family'
      when 'invitation_applied_body' then 'Review the family invitation to accept or decline.'
      when 'invitation_applied_public_body' then 'You have a family invitation update. Unlock to view it.'
      when 'invitation_decided_title' then case when p_status = 'accepted' then 'Family invitation accepted' else 'Family invitation not accepted' end
      when 'invitation_decided_body' then case when p_status = 'accepted' then 'You can now care for your family together in Munea.' else 'Check with your family member before sending another invitation.' end
      when 'invitation_decided_public_body' then 'Your family invitation has a new result. Unlock to view it.'
      else 'Munea Reminder'
    end
    when 'ja' then case p_key
      when 'generic_title' then 'Muneaからのお知らせ'
      when 'generic_body' then '健康に関するお知らせがあります。ロックを解除して確認してください。'
      when 'family_relay_title' then coalesce(nullif(p_sender_label, ''), 'ご家族') || 'さんからメッセージが届きました'
      when 'family_relay_public_body' then 'ご家族からメッセージが届きました。ロックを解除して再生できます。'
      when 'invitation_applied_title' then '家族への参加申請が届きました'
      when 'invitation_applied_body' then '家族の招待画面で承認するか確認してください。'
      when 'invitation_applied_public_body' then '家族の招待に更新があります。ロックを解除して確認してください。'
      when 'invitation_decided_title' then case when p_status = 'accepted' then '家族の招待が承認されました' else '家族の招待は承認されませんでした' end
      when 'invitation_decided_body' then case when p_status = 'accepted' then 'Muneaで一緒にご家族を見守れるようになりました。' else 'ご家族と確認してから、もう一度招待してください。' end
      when 'invitation_decided_public_body' then '家族の招待結果が更新されました。ロックを解除して確認してください。'
      else 'Muneaからのお知らせ'
    end
    when 'es' then case p_key
      when 'generic_title' then 'Recordatorio de Munea'
      when 'generic_body' then 'Tienes un recordatorio de salud. Desbloquea para verlo.'
      when 'family_relay_title' then coalesce(nullif(p_sender_label, ''), 'Un familiar') || ' te envió un mensaje'
      when 'family_relay_public_body' then 'Un familiar te envió un mensaje. Desbloquea para escucharlo.'
      when 'invitation_applied_title' then 'Un familiar solicitó unirse a tu familia'
      when 'invitation_applied_body' then 'Revisa la invitación familiar para aceptarla o rechazarla.'
      when 'invitation_applied_public_body' then 'Hay una actualización de invitación familiar. Desbloquea para verla.'
      when 'invitation_decided_title' then case when p_status = 'accepted' then 'Invitación familiar aceptada' else 'Invitación familiar no aceptada' end
      when 'invitation_decided_body' then case when p_status = 'accepted' then 'Ahora pueden cuidar juntos de su familia en Munea.' else 'Consulta con tu familiar antes de enviar otra invitación.' end
      when 'invitation_decided_public_body' then 'Tu invitación familiar tiene un nuevo resultado. Desbloquea para verlo.'
      else 'Recordatorio de Munea'
    end
    else case p_key
      when 'generic_title' then '沐寧提醒'
      when 'generic_body' then '你的健康提醒到了，解鎖後查看。'
      when 'family_relay_title' then coalesce(nullif(p_sender_label, ''), '家人') || '捎來一則話'
      when 'family_relay_public_body' then '家人捎來一則訊息，解鎖後收聽。'
      when 'invitation_applied_title' then '家人申請加入你的家庭'
      when 'invitation_applied_body' then '請到家庭邀請確認是否接受。'
      when 'invitation_applied_public_body' then '你有一則家庭邀請更新，解鎖後查看。'
      when 'invitation_decided_title' then case when p_status = 'accepted' then '家庭邀請已接受' else '家庭邀請未接受' end
      when 'invitation_decided_body' then case when p_status = 'accepted' then '你現在可以在沐寧一起照顧家人。' else '請與家人確認後再重新邀請。' end
      when 'invitation_decided_public_body' then '你的家庭邀請已有新結果，解鎖後查看。'
      else '沐寧提醒'
    end
  end;
$$;

revoke all on function public.notification_copy(text, text, text, text) from public, anon, authenticated;
grant execute on function public.notification_copy(text, text, text, text) to service_role;


create or replace function public.notify_family_relay_created()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_locale text := public.notification_locale_for_person(new.recipient_person_id);
begin
  perform public.enqueue_notification_event(
    new.recipient_person_id,
    'family_relay',
    public.notification_copy(v_locale, 'family_relay_title', new.sender_label),
    new.content,
    public.notification_copy(v_locale, 'generic_title'),
    public.notification_copy(v_locale, 'family_relay_public_body'),
    'private',
    'munea://relay/' || new.id::text,
    new.sender_person_id,
    new.family_group_id,
    'family_relay_message',
    new.id::text,
    'family-relay:' || new.id::text,
    jsonb_build_object('source', new.source, 'locale', v_locale, 'senderLabel', new.sender_label),
    new.expires_at
  );
  return new;
end;
$$;

revoke all on function public.notify_family_relay_created() from public, anon, authenticated;


create or replace function public.notify_family_invitation_changed()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_recipient_person_id uuid;
  v_actor_person_id uuid;
  v_event_type text;
  v_copy_prefix text;
  v_locale text;
  v_dedupe_key text;
begin
  if new.status = 'applied'
     and new.status is distinct from old.status
     and new.inviter_person_id is not null
     and new.invitee_person_id is not null then
    v_recipient_person_id := new.inviter_person_id;
    v_actor_person_id := new.invitee_person_id;
    v_event_type := 'invitation_applied';
    v_copy_prefix := 'invitation_applied';
    v_dedupe_key := 'family-invitation-applied:' || new.id::text;
  elsif new.status in ('accepted', 'rejected')
        and new.status is distinct from old.status
        and new.inviter_person_id is not null
        and new.invitee_person_id is not null then
    v_recipient_person_id := new.invitee_person_id;
    v_actor_person_id := new.inviter_person_id;
    v_event_type := 'invitation_decided';
    v_copy_prefix := 'invitation_decided';
    v_dedupe_key := 'family-invitation-decided:' || new.id::text || ':' || new.status;
  else
    return new;
  end if;

  v_locale := public.notification_locale_for_person(v_recipient_person_id);
  perform public.enqueue_notification_event(
    v_recipient_person_id,
    v_event_type,
    public.notification_copy(v_locale, v_copy_prefix || '_title', null, new.status),
    public.notification_copy(v_locale, v_copy_prefix || '_body', null, new.status),
    public.notification_copy(v_locale, 'generic_title'),
    public.notification_copy(v_locale, v_copy_prefix || '_public_body', null, new.status),
    'private',
    'munea://family/invitations/' || new.id::text,
    v_actor_person_id,
    new.family_group_id,
    'family_invitation',
    new.id::text,
    v_dedupe_key,
    jsonb_build_object('decision', new.status, 'locale', v_locale),
    new.expires_at
  );
  return new;
end;
$$;

revoke all on function public.notify_family_invitation_changed() from public, anon, authenticated;
