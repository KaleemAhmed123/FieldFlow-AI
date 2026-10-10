"""One-time admin login to mint the Hosted-MCP refresh token (OAuth2 + PKCE).

Hosted MCP has no headless client-credentials grant, so the admin authorizes ONCE in a browser and
we capture a long-lived refresh token. The MCP client (app/mcp/client.py) then swaps that for access
tokens on its own — no further logins. Run it once:

    cd apps/orchestrator
    uv run python -m app.mcp.login

It reads SF_MCP_SERVER_URL / SF_MCP_CLIENT_ID / SF_MCP_CLIENT_SECRET from your .env, opens the
Salesforce login page, captures the redirect on http://localhost:8000/oauth/callback (this MUST
match the ECA's Callback URL), and prints SF_MCP_REFRESH_TOKEN for you to paste into .env.

PKCE (Proof Key for Code Exchange): a one-time secret the client proves it owns, so an intercepted
auth code is useless. Salesforce requires it for Hosted MCP.

# ponytail: stdlib only (no extra dep) — a tiny localhost callback server, used once by a human.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from urllib.parse import urlsplit

from app.config import settings


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _capture_code(port: int) -> str:
    """Serve the ECA redirect once and return the `code` query param."""
    box: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            q = urllib.parse.parse_qs(urlsplit(self.path).query)
            box["code"] = q.get("code", [""])[0]
            box["error"] = q.get("error_description", q.get("error", [""]))[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = "FieldFlow: login captured — you can close this tab." if box["code"] else \
                  f"FieldFlow: login failed — {box['error']}"
            self.wfile.write(f"<h3>{msg}</h3>".encode())

        def log_message(self, *args: object) -> None:  # silence the default stderr spam
            return

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.handle_request()  # blocks for exactly one request (the redirect)
    server.server_close()
    if not box.get("code"):
        sys.exit(f"login failed: {box.get('error') or 'no code returned'}")
    return box["code"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Mint the Hosted-MCP refresh token (one time).")
    ap.add_argument("--scope", default="refresh_token api mcp_api",
                    help="OAuth scopes — must be a subset of the ECA's scopes.")
    ap.add_argument("--port", type=int, default=8000, help="Local callback port (match the ECA).")
    args = ap.parse_args()

    if not (settings.sf_mcp_server_url and settings.sf_mcp_client_id
            and settings.sf_mcp_client_secret):
        sys.exit("Set SF_MCP_SERVER_URL + SF_MCP_CLIENT_ID + SF_MCP_CLIENT_SECRET in .env first.")

    origin = _origin(settings.sf_mcp_token_url or settings.sf_mcp_server_url)
    redirect_uri = f"http://localhost:{args.port}/oauth/callback"
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    authorize = f"{origin}/services/oauth2/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": settings.sf_mcp_client_id,
        "redirect_uri": redirect_uri, "scope": args.scope,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })

    print("Opening the Salesforce login page. Log in as the admin and approve.\n")
    print(authorize + "\n")
    webbrowser.open(authorize)
    code = _capture_code(args.port)

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": settings.sf_mcp_client_id, "client_secret": settings.sf_mcp_client_secret,
        "code_verifier": verifier,
    }).encode()
    token_url = settings.sf_mcp_token_url or f"{origin}/services/oauth2/token"
    try:
        with urllib.request.urlopen(urllib.request.Request(token_url, data=data)) as r:  # noqa: S310
            body = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"token exchange failed ({e.code}): {e.read().decode(errors='replace')}")

    rt = body.get("refresh_token")
    if not rt:
        sys.exit(f"no refresh_token in response (scopes missing refresh_token?): {body}")
    print("\n✅ Success. Paste this into apps/orchestrator/.env:\n")
    print(f"SF_MCP_REFRESH_TOKEN={rt}")


if __name__ == "__main__":
    main()
