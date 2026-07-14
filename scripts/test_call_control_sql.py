"""Static regression checks for the realtime call-control migration."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "supabase" / "sql" / "010_realtime_call_control.sql"
SQL = SQL_PATH.read_text(encoding="utf-8")
NORMALIZED_SQL = re.sub(r"\s+", "", SQL.lower())


def function_body(name: str) -> str:
    match = re.search(
        rf"create\s+or\s+replace\s+function\s+public\.{name}\s*\(.*?"
        rf"\)\s+returns\s+.*?\bas\s+\$\$(.*?)\$\$;",
        SQL,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing function body: {name}"
    return re.sub(r"\s+", " ", match.group(1).lower()).strip()


def assert_in_order(body: str, *fragments: str) -> None:
    position = -1
    for fragment in fragments:
        next_position = body.find(fragment, position + 1)
        assert next_position >= 0, f"missing SQL fragment: {fragment}"
        assert next_position > position, f"SQL fragment out of order: {fragment}"
        position = next_position


def test_release_signature_matches_definition() -> None:
    correct = "public.munea_call_release(uuid,integer,text,text,uuid)"
    wrong = "public.munea_call_release(uuid,integer,text,text,text,uuid)"
    assert NORMALIZED_SQL.count(correct) == 2, "release revoke/grant must use five arguments"
    assert wrong not in NORMALIZED_SQL, "stale six-argument release signature remains"


def test_credit_reservation_is_atomic_with_consumption() -> None:
    request = function_body("munea_call_request")
    consume = function_body("munea_call_consume_credit")

    assert_in_order(
        request,
        "hashtextextended(v_account_id::text, 724338221)",
        "from public.credit_wallets",
        "for update",
        "select coalesce(sum(balance),0) into v_available",
        "select coalesce(sum(amount),0) into v_holds",
        "if v_available - v_holds < 1",
        "insert into public.call_credit_holds",
    )
    assert_in_order(
        consume,
        "hashtextextended(p_account_id::text, 724338221)",
        "from public.credit_wallets",
        "for update",
        "select coalesce(sum(balance), 0) into v_available",
        "select coalesce(sum(amount), 0) into v_holds",
        "and call_id <> p_call_id",
        "if v_available - v_holds < 1",
        "update public.credit_wallets",
    )


def test_reaper_bills_before_releasing_capacity() -> None:
    reaper = function_body("munea_call_reap_expired")
    assert "ceil(greatest(0, extract(epoch from (now() - v_row.active_at))) / 60.0)" in reaper
    assert_in_order(
        reaper,
        "for v_minute in (v_billed + 1)..v_target loop",
        "perform public.munea_call_consume_credit",
        "v_billed := v_minute",
        "exception when raise_exception",
        "update public.gpu_workers",
        "update public.voice_shards",
        "set state = 'failed'",
    )
    assert "billed_credits = greatest(billed_credits, v_billed)" in reaper


def test_final_release_bills_before_releasing_capacity() -> None:
    release = function_body("munea_call_release")
    assert "ceil(greatest(0,extract(epoch from (now()-v_call.active_at)))/60.0)" in release
    assert_in_order(
        release,
        "for v_minute in (v_billed+1)..v_target loop",
        "perform public.munea_call_consume_credit",
        "v_billed := v_minute",
        "exception when raise_exception",
        "update public.gpu_workers",
        "update public.voice_shards",
        "set state='ended'",
    )
    assert "billed_credits=greatest(billed_credits,v_billed)" in release


def main() -> None:
    tests = [
        test_release_signature_matches_definition,
        test_credit_reservation_is_atomic_with_consumption,
        test_reaper_bills_before_releasing_capacity,
        test_final_release_bills_before_releasing_capacity,
    ]
    for test in tests:
        test()
        print(f"{test.__name__}: PASS")
    print("Realtime call-control SQL contract: ALL PASS")


if __name__ == "__main__":
    main()
