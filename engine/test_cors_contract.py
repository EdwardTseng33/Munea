#!/usr/bin/env python3
"""Launch contract for Capacitor/Web cross-origin access to the Brain API."""
from pathlib import Path


source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")


def require(label, token):
    if token not in source:
        raise AssertionError(f"{label}: missing {token!r}")
    print(f"PASS {label}")


require("Capacitor origin", '"capacitor://localhost"')
require("production Web origin", '"https://app.munea.net"')
require("OPTIONS handler", "def do_OPTIONS(self):")
require("origin reflection", '"Access-Control-Allow-Origin"')
require("origin cache isolation", '"Vary", "Origin"')
require("app key preflight header", "X-Munea-Key")
require("authorization preflight header", "Authorization, Content-Type")
require("no wildcard credential origin", 'origin in cors_origins()')

print("CORS launch contract PASS")
