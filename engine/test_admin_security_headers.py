#!/usr/bin/env python3
"""Contract tests for the operations console response security policy."""
import io
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "admin-security-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


def response_headers(path, content_type, extra_headers=None):
    handler = server.H.__new__(server.H)
    handler.path = path
    handler.headers = {}
    handler.wfile = io.BytesIO()
    captured = {}
    handler.send_response = lambda code: captured.update({":status": str(code)})
    handler.send_header = lambda name, value: captured.update({name: str(value)})
    handler.end_headers = lambda: None
    handler._send(200, content_type, b"ok", extra_headers=extra_headers)
    return captured


def require(label, condition):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


admin_html = response_headers("/admin.html?view=overview", "text/html; charset=utf-8")
require("admin HTML cannot be framed", admin_html.get("X-Frame-Options") == "DENY")
require("admin HTML disables MIME sniffing", admin_html.get("X-Content-Type-Options") == "nosniff")
require("admin HTML hides referrer", admin_html.get("Referrer-Policy") == "no-referrer")

csp = admin_html.get("Content-Security-Policy", "")
for directive in (
    "default-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "object-src 'none'",
    "script-src 'self'",
    "connect-src 'self' https://*.run.app https://*.a.run.app",
):
    require(f"admin CSP has {directive}", directive in csp)
require("admin script policy has no unsafe-inline", "script-src 'self' 'unsafe-inline'" not in csp)
require("admin CSP has no unsafe-eval", "'unsafe-eval'" not in csp)

admin_api = response_headers(
    "/admin/usage",
    "application/json; charset=utf-8",
    extra_headers={"Retry-After": "60", "X-Frame-Options": "SAMEORIGIN"},
)
require("admin API keeps functional headers", admin_api.get("Retry-After") == "60")
require("admin API security header cannot be weakened", admin_api.get("X-Frame-Options") == "DENY")
require("admin API has no document CSP", "Content-Security-Policy" not in admin_api)

admin_asset = response_headers("/src/admin.js", "application/javascript; charset=utf-8")
require("admin asset disables MIME sniffing", admin_asset.get("X-Content-Type-Options") == "nosniff")
require("admin asset has no document CSP", "Content-Security-Policy" not in admin_asset)

app_page = response_headers("/index.html", "text/html; charset=utf-8")
require("regular app is outside admin CSP", "Content-Security-Policy" not in app_page)
require("regular app framing policy is unchanged", "X-Frame-Options" not in app_page)

# 機構專區（照護人員版）：防嵌框只能靠標頭；頁面自己的 meta CSP 管其他的，標頭這邊只放 frame-ancestors
org_html = response_headers("/org.html?demo=1", "text/html; charset=utf-8")
require("org portal HTML cannot be framed", org_html.get("X-Frame-Options") == "DENY")
require("org portal HTML disables MIME sniffing", org_html.get("X-Content-Type-Options") == "nosniff")
require("org portal HTML hides referrer", org_html.get("Referrer-Policy") == "no-referrer")
require("org portal HTML header CSP is only frame-ancestors", org_html.get("Content-Security-Policy") == "frame-ancestors 'none'")
for asset, ctype in (("/src/org.js", "application/javascript; charset=utf-8"), ("/src/org.css", "text/css; charset=utf-8")):
    asset_headers = response_headers(asset, ctype)
    require(f"{asset} disables MIME sniffing", asset_headers.get("X-Content-Type-Options") == "nosniff")
    require(f"{asset} cannot be framed", asset_headers.get("X-Frame-Options") == "DENY")
    require(f"{asset} hides referrer", asset_headers.get("Referrer-Policy") == "no-referrer")
    require(f"{asset} has no document CSP", "Content-Security-Policy" not in asset_headers)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "org.html"), encoding="utf-8") as fh:
    org_meta = fh.read()
require("org portal page still carries its own meta CSP", 'http-equiv="Content-Security-Policy"' in org_meta)
require("org portal meta CSP does not rely on frame-ancestors (ignored in meta)", "frame-ancestors" not in org_meta)
# 拿得到同一個檔的寫法（結尾斜線、雙斜線、繞一圈的路徑），標頭也要一樣（#722 信任關卡）
for raw in ("/org.html/", "//org.html", "/src/../org.html", "/./org.html?demo=1"):
    variant = response_headers(raw, "text/html; charset=utf-8")
    require(f"{raw} gets the org portal headers",
            variant.get("X-Frame-Options") == "DENY" and variant.get("Content-Security-Policy") == "frame-ancestors 'none'")
admin_variant = response_headers("/admin.html/", "text/html; charset=utf-8")
require("/admin.html/ still gets the admin CSP",
        "frame-ancestors 'none'" in admin_variant.get("Content-Security-Policy", "") and admin_variant.get("X-Frame-Options") == "DENY")
require("/src/org.js/ disables MIME sniffing", response_headers("/src/org.js/", "application/javascript; charset=utf-8").get("X-Content-Type-Options") == "nosniff")
require("header path normalizes like file serving", server.normalized_request_path("/src/../org.html") == "/org.html"
        and server.normalized_request_path("//org.html") == "/org.html" and server.normalized_request_path("/") == "/")
link_portal = response_headers("/org-portal.html", "text/html; charset=utf-8")
require("link-based org portal is unchanged", "Content-Security-Policy" not in link_portal and "X-Frame-Options" not in link_portal)

print("Admin security header contract PASS")
