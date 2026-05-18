#!/usr/bin/env python3
"""Smoke test the local Dex auth-code flow used by M2.2-AUTH-FINAL.

This script expects Dex from deploy/docker/config/dex-dev.yaml to be running.
It intentionally uses only the Python standard library so it can run in CI and
offline developer environments after Docker images are available.
"""

from __future__ import annotations

import argparse
import base64
import html.parser
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


class LoginFormParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.form_action = ""
        self.inputs: dict[str, str] = {}
        self._in_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "form" and not self.form_action:
            self._in_form = True
            self.form_action = values.get("action", "")
            return
        if self._in_form and tag == "input":
            name = values.get("name", "")
            if name:
                self.inputs[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._in_form:
            self._in_form = False


def request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=encoded, method=method, headers=headers or {})
    try:
        with opener.open(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


def wait_for_dex(opener: urllib.request.OpenerDirector, issuer: str, timeout_seconds: int) -> dict:
    discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _, body = request(opener, "GET", discovery_url)
            if status == 200:
                return json.loads(body.decode())
            last_error = RuntimeError(f"{discovery_url} returned HTTP {status}")
        except Exception as err:  # pragma: no cover - smoke script diagnostics
            last_error = err
        time.sleep(1)
    raise RuntimeError(f"Dex discovery did not become ready: {last_error}")


def follow_until_redirect(
    opener: urllib.request.OpenerDirector,
    url: str,
    redirect_prefix: str,
    *,
    max_hops: int = 8,
) -> str:
    current = url
    for _ in range(max_hops):
        if current.startswith(redirect_prefix):
            return current
        status, headers, _ = request(opener, "GET", current)
        location = headers.get("Location", "")
        if status not in (301, 302, 303, 307, 308) or not location:
            raise RuntimeError(f"expected redirect from {current}, got HTTP {status}")
        next_url = urllib.parse.urljoin(current, location)
        if next_url.startswith(redirect_prefix):
            return next_url
        current = next_url
    raise RuntimeError("too many redirects before callback")


def get_login_page(
    opener: urllib.request.OpenerDirector,
    url: str,
    redirect_prefix: str,
    *,
    max_hops: int = 8,
) -> tuple[str, bytes]:
    current = url
    for _ in range(max_hops):
        status, headers, body = request(opener, "GET", current)
        if status == 200:
            return current, body
        location = headers.get("Location", "")
        if status not in (301, 302, 303, 307, 308) or not location:
            raise RuntimeError(f"expected login page or redirect from {current}, got HTTP {status}")
        next_url = urllib.parse.urljoin(current, location)
        if next_url.startswith(redirect_prefix):
            raise RuntimeError("authorization redirected to callback before login")
        current = next_url
    raise RuntimeError("too many redirects before login page")


def parse_login_form(body: bytes, base_url: str) -> tuple[str, dict[str, str]]:
    parser = LoginFormParser()
    parser.feed(body.decode(errors="replace"))
    if not parser.form_action:
        raise RuntimeError("Dex login form action not found")
    return urllib.parse.urljoin(base_url, parser.form_action), parser.inputs


def run(args: argparse.Namespace) -> None:
    cookies = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies),
        NoRedirect(),
    )
    discovery = wait_for_dex(opener, args.issuer, args.timeout_seconds)
    if discovery.get("issuer") != args.issuer:
        raise RuntimeError(f"issuer mismatch: {discovery.get('issuer')!r}")

    status, _, jwks_body = request(opener, "GET", discovery["jwks_uri"])
    if status != 200:
        raise RuntimeError(f"JWKS endpoint returned HTTP {status}")
    jwks = json.loads(jwks_body.decode())
    if not jwks.get("keys"):
        raise RuntimeError("JWKS did not contain signing keys")

    state = "ani-smoke-state"
    auth_query = urllib.parse.urlencode(
        {
            "client_id": args.client_id,
            "redirect_uri": args.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile groups offline_access",
            "state": state,
            "nonce": "ani-smoke-nonce",
        }
    )
    auth_url = discovery["authorization_endpoint"] + "?" + auth_query
    login_page_url, body = get_login_page(opener, auth_url, args.redirect_uri)
    login_url, form = parse_login_form(body, login_page_url)
    form.update({"login": args.username, "password": args.password})
    status, headers, _ = request(opener, "POST", login_url, data=form)
    if status not in (301, 302, 303):
        raise RuntimeError(f"login submit returned HTTP {status}")

    redirect = urllib.parse.urljoin(login_url, headers["Location"])
    callback_url = follow_until_redirect(opener, redirect, args.redirect_uri)
    callback = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(callback.query)
    if params.get("state", [""])[0] != state:
        raise RuntimeError("callback state mismatch")
    code = params.get("code", [""])[0]
    if not code:
        raise RuntimeError("authorization code missing from callback")

    basic = base64.b64encode(f"{args.client_id}:{args.client_secret}".encode()).decode()
    status, _, token_body = request(
        opener,
        "POST",
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": args.redirect_uri,
        },
        headers={"Authorization": f"Basic {basic}"},
    )
    if status != 200:
        raise RuntimeError(f"token endpoint returned HTTP {status}: {token_body.decode(errors='replace')}")
    token = json.loads(token_body.decode())
    for field in ("access_token", "id_token", "refresh_token", "expires_in"):
        if field not in token:
            raise RuntimeError(f"token response missing {field}")
    print("Dex auth-code smoke passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issuer", default="http://127.0.0.1:5556/dex")
    parser.add_argument("--client-id", default="ani-console")
    parser.add_argument("--client-secret", default="ani-console-secret")
    parser.add_argument("--redirect-uri", default="http://127.0.0.1:3000/auth/callback")
    parser.add_argument("--username", default="admin@ani.local")
    parser.add_argument("--password", default="ani-dev-password")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
