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

print("Admin security header contract PASS")
