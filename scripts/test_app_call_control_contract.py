"""Static launch contract for the App-to-Call-Control handoff."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "src" / "app.js").read_text(encoding="utf-8")
PACKAGE = (ROOT / "package.json").read_text(encoding="utf-8")
VOICE_DEPLOY = (ROOT / "scripts" / "cloud-run-deploy-staging.ps1").read_text(
    encoding="utf-8"
)
VERCEL_CONFIG = (ROOT / "app-site" / "vercel.json").read_text(encoding="utf-8")
AUTH_CONFIG = (ROOT / "web" / "src" / "auth-config.js").read_text(encoding="utf-8")
DEV_PROFILE = (ROOT / "scripts" / "enable-ios-development-profile.mjs").read_text(
    encoding="utf-8"
)


def test_production_app_uses_gateway_by_default() -> None:
    assert (
        "const CALL_CONTROL_URL_DEFAULT = "
        "'https://munea-call-control-fiu65jd4da-de.a.run.app';"
    ) in APP
    assert "if (CallControl.url()) {" not in APP
    assert "await CallControl.acquire(" in APP


def test_cancelled_acquire_disposes_returned_capacity() -> None:
    assert "const generation = ++this.generation;" in APP
    assert "generation !== this.generation" in APP
    assert "await this._disposeResult(result, 'cancelled_during_acquire')" in APP
    assert "this.generation += 1;" in APP


def test_development_profile_bypass_does_not_weaken_release() -> None:
    assert "bypassCallControl: false" in AUTH_CONFIG
    assert "bypassCallControl: true" in DEV_PROFILE
    assert "function usesDevelopmentDirectCall()" in APP
    assert "if (usesDevelopmentDirectCall()) return '';" in APP
    assert "if (!developmentDirectCall)" in APP
    assert "if (!developmentDirectCall) await CallControl.waitUntilActive(15000);" in APP


def test_voice_and_avatar_are_a_single_required_service() -> None:
    assert "!lease.voice || !lease.voice.url" in APP
    assert "!lease.worker || !lease.worker.url" in APP
    assert "throw new Error('paired_service_unavailable')" in APP
    assert "if (CallControl.active) return (CallControl.active.voice" in APP
    assert "if (CallControl.active) return (CallControl.active.worker" in APP


def test_connected_ui_waits_for_server_active_lease() -> None:
    assert "async waitUntilActive(timeoutMs = 15000)" in APP
    assert "result.state === 'active'" in APP
    assert "await CallControl.waitUntilActive(15000);" in APP
    assert APP.index("await CallControl.waitUntilActive(15000);") < APP.index("markConnected();")


def test_gateway_billing_replaces_local_point_mutation() -> None:
    assert "const serverAuthoritative = Boolean(CallControl.url());" in APP
    assert "trackedSession && !serverAuthoritative" in APP
    assert "billedCredits: result && result.billed_credits" in APP
    assert "refreshServerCredits();" in APP
    assert "POINTS.serverRemaining" in APP


def test_app_cannot_mark_provider_components_ready() -> None:
    assert "/internal/calls/" not in APP


def test_retired_agent_lock_script_is_not_exposed() -> None:
    assert "test:agent-locks" not in PACKAGE
    assert "test-agent-lock.py" not in PACKAGE


def test_voice_deploy_wires_call_control_without_breaking_old_app() -> None:
    assert "MUNEA_CALL_CONTROL_URL=$CallControlUrl" in VOICE_DEPLOY
    assert "MUNEA_GATEWAY_ADMIN_KEY=$($GatewayAdminSecret):latest" in VOICE_DEPLOY
    assert "MUNEA_CALL_TOKEN_SECRET=$($CallTokenSecret):latest" in VOICE_DEPLOY
    assert "MUNEA_VOICE_SHARD_ID=$VoiceShardId" in VOICE_DEPLOY
    assert "$callControlRequired = if ($RequireCallControl)" in VOICE_DEPLOY


def test_vercel_preview_comments_are_silent() -> None:
    assert '"github"' in VERCEL_CONFIG
    assert '"silent": true' in VERCEL_CONFIG


def main() -> None:
    tests = [
        test_production_app_uses_gateway_by_default,
        test_cancelled_acquire_disposes_returned_capacity,
        test_development_profile_bypass_does_not_weaken_release,
        test_voice_and_avatar_are_a_single_required_service,
        test_connected_ui_waits_for_server_active_lease,
        test_gateway_billing_replaces_local_point_mutation,
        test_app_cannot_mark_provider_components_ready,
        test_retired_agent_lock_script_is_not_exposed,
        test_voice_deploy_wires_call_control_without_breaking_old_app,
        test_vercel_preview_comments_are_silent,
    ]
    for test in tests:
        test()
        print(f"{test.__name__}: PASS")
    print("App Call Control contract: ALL PASS")


if __name__ == "__main__":
    main()
