# oauthlib 3.3.1 — public API reference (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/oauthlib/`, pure Python, `Requires-Python: >=3.8`,
> BSD-3-Clause). Transitive dependency only — **not** in the app's
> `pyproject.toml` `dependencies` list. Evidence for every claim below.

`Name: oauthlib, Version: 3.3.1` (from `oauthlib-3.3.1.dist-info/METADATA`).
Verified live: `uv run python -c "import oauthlib"` → `oauthlib 3.3.1`.

## 1. Dependency chain: why it is installed

- App declares `flet==0.85.3` in `pyproject.toml`; no direct mention of
  `oauthlib` anywhere in `src/` (grep for `login|logout|auth|OAuth` in `src/`
  returns zero hits).
- `flet-0.85.3.dist-info/METADATA` contains:
  `Requires-Dist: oauthlib>=3.2.2; platform_system != "Emscripten"`.
- So: `animepahe-tv → flet → oauthlib`. Removing flet removes oauthlib;
  nothing else in the venv requires it.

## 2. What flet uses it for (all three call sites)

The **only** flet module that imports oauthlib is
`flet/auth/authorization_service.py` (`AuthorizationService`, used by
`Page.login`). Grep over the whole `flet/` package shows exactly three
imports, all `from oauthlib.oauth2 import WebApplicationClient`:

| Line | Method | oauthlib call | Purpose |
|---|---|---|---|
| 94–107 | `get_authorization_data()` | `WebApplicationClient(client_id).prepare_request_uri(auth_endpoint, redirect_uri, scope, state, code_challenge, code_challenge_method, **extra)` | Build the login redirect URL + CSRF `state` (`secrets.token_urlsafe(16)`). Returns `(authorization_url, state)` tuple. |
| 120–141 | `request_token(code)` | `prepare_request_body(code, redirect_uri, client_secret, include_client_id=True, code_verifier)` → POST via `httpx.AsyncClient` → `parse_request_body_response(resp.text)` | Authorization-code exchange. oauthlib builds the `application/x-www-form-urlencoded` body and parses the JSON token response into a dict; flet converts it to `OAuthToken` via `__convert_token`. |
| 208–232 | `__refresh_token()` | `prepare_refresh_body(client_id, client_secret, refresh_token, redirect_uri)` → POST via httpx → `parse_request_body_response(...)` | Silent token refresh (see §5). |

Key detail: oauthlib is used **only as a request-body/URL builder + response
parser**. All HTTP is done by `httpx` (`httpx.Request` + `httpx.AsyncClient`),
all token state lives in flet's own `OAuthToken` class, user/group fetching
is flet's own `OAuthProvider._fetch_user/_fetch_groups` hooks. oauthlib never
touches the network.

`Page.login` is the only entry point: `AuthorizationService` coordinates
`get_authorization_data → (browser redirect) → request_token → get_token`.
The `flet pubsub` ("publish") modules (`pubsub_hub.py`, `pubsub_client.py`)
contain zero oauthlib references — oauthlib has nothing to do with
flet publish.

## 3. Public client classes (`oauthlib.oauth2`)

From `oauthlib/oauth2/__init__.py` — the RFC 6749 client-side API:

```python
from oauthlib.oauth2 import (
    WebApplicationClient,      # authorization-code flow (confidential clients) — the one flet uses
    MobileApplicationClient,   # implicit flow (public / browser clients)
    LegacyApplicationClient,   # resource-owner-password-credentials flow
    BackendApplicationClient,  # client-credentials flow
    ServiceApplicationClient,  # JWT bearer (RFC 7523) client assertion
    DeviceClient,              # device-code flow (RFC 8628)
    Client,                    # base class, all shared logic lives here
)
```

Per-flow one-liners (`rfc6749/clients/*.py`):

- `WebApplicationClient(client_id, code=None)` — `grant_type =
  'authorization_code'`. `prepare_request_uri(...)` adds `response_type=code`
  + `client_id`; `prepare_request_body(code, redirect_uri, ...)` builds the
  code-exchange body.
- `MobileApplicationClient` — implicit flow, token comes back in redirect
  fragment; `parse_request_uri_response`.
- `LegacyApplicationClient` — `prepare_request_body(username, password, ...)`.
- `BackendApplicationClient` — `prepare_request_body(scope, ...)` with
  `grant_type=client_credentials`.
- `ServiceApplicationClient` — JWT assertion preparation.
- `DeviceClient` (`rfc8628/clients/device.py`) — device authorization flow.

Server-side mirrors (`AuthorizationEndpoint`, `TokenEndpoint`,
`WebApplicationServer`, `DeviceApplicationServer`, grant types
`AuthorizationCodeGrant`, `RefreshTokenGrant`, `DeviceCodeGrant`, …) exist in
`oauthlib.oauth2.rfc6749.endpoints / grant_types` but flet never imports them.

Verified live method list on `WebApplicationClient('id')`:

```python
['add_token', 'parse_request_body_response', 'parse_request_uri_response',
 'prepare_authorization_request', 'prepare_refresh_body',
 'prepare_refresh_token_request', 'prepare_request_body',
 'prepare_request_uri', 'prepare_token_request',
 'prepare_token_revocation_request']
```

Most useful signatures (from `rfc6749/clients/base.py` + `web_application.py`):

```python
Client.prepare_refresh_token_request(token_url, refresh_token=None, body='', scope=None, **kwargs)
    -> (url, headers, body)   # full request tuple, HTTPS-enforced (InsecureTransportError otherwise)

Client.parse_request_body_response(body, scope=None, **kwargs) -> dict
    # parses JSON token response; populates .token/.access_token/.refresh_token/
    # .expires_in/.expires_at; raises OAuth2Error subclass on error payload

Client.add_token(uri, http_method='GET', body=None, headers=None, token_placement=None)
    # injects Bearer (default, Authorization header) or MAC token; raises
    # TokenExpiredError if ._expires_at passed, InsecureTransportError on http://

Client.prepare_token_revocation_request(revocation_url, token, token_type_hint='access_token', ...)
```

Token placement constants from `rfc6749/clients/__init__.py`:
`AUTH_HEADER = 'auth_header'` (default), `URI_QUERY = 'query'`, `BODY = 'body'`.

## 4. OAuth1 + OpenID surface (for completeness, unused by flet)

- `oauthlib.oauth1.rfc5849`: `Client`, signature methods
  (`SIGNATURE_HMAC_SHA1/SHA256/PLAINTEXT`, RSA via `cryptography` extra),
  endpoints (`RequestTokenEndpoint`, `AuthorizationEndpoint`,
  `AccessTokenEndpoint`, `ResourceEndpoint`, `SignatureOnlyEndpoint`).
- `oauthlib.openid`: `openid/__init__.py` exists but is effectively a stub
  (no grant logic; OpenID Connect user-info handling lives in flet providers).
- `oauthlib.common`: `generate_token`, `urldecode`, `quote/unquote`,
  `Request`/`Response` wrappers. `oauthlib.signals`: blinker-based
  (`signals` extra, not installed). `oauthlib.uri_validate`: `is_valid_uri`.

## 5. Token refresh flow (the one flet actually exercises)

oauthlib side (`Client.prepare_refresh_body`, `base.py:430`):

```python
def prepare_refresh_body(self, body='', refresh_token=None, scope=None, **kwargs):
    refresh_token = refresh_token or self.refresh_token
    scope = self.scope if scope is None else scope
    return prepare_token_request('refresh_token', body=body, scope=scope,
                                 refresh_token=refresh_token, **kwargs)
```

i.e. it URL-encodes `grant_type=refresh_token&refresh_token=...`
(+ optional narrowed `scope`, client credentials passed as kwargs).

Flet side (`AuthorizationService.__refresh_token`, lines 188–232) — the
policy wrapper:

1. No-op unless **all** hold: token exists, `expires_at` is set,
   `refresh_token` present, `time.time() >= expires_at`.
2. Builds refresh body via oauthlib, POSTs with httpx
   (`content-type: application/x-www-form-urlencoded`, `User-Agent: Flet/<ver>`).
3. Parses with `parse_request_body_response`; if the response omits a new
   `refresh_token`, the old one is preserved
   (`t["refresh_token"] = self.__token.refresh_token`) — rolling-refresh safe.
4. Replaces `self.__token` with fresh `OAuthToken`. `expires_at` is an
   absolute epoch float; a token with `expires_at=None` never refreshes.

`dehydrate_token(saved_token)` / `get_token()` both funnel through
`__refresh_token`, so restore-from-storage and every token read get the same
refresh-on-expiry behavior.

## 6. Does our app have ANY use for it? No.

Evidence:

1. `pyproject.toml` `[project] dependencies` = `flet`, `flet-video`,
   `flet-webview`, `flet-yandex-ads`, `flet-notifications`, `primp` — no
   `oauthlib`, no `httpx` direct use for auth.
2. Grep of `src/` for `login|logout|auth|OAuth|AuthorizationService|
   OAuthProvider|OAuthToken` → **zero matches**. The app never calls
   `page.login()`, never constructs an `OAuthProvider`
   (`Auth0/Azure/GitHub/Google` subclasses in `flet/auth/providers/`),
   never touches `AuthorizationService`.
3. The app's auth-adjacent behavior (AnimePahe session handling) is done with
   `primp` in `src/services/animepahe.py`, unrelated to OAuth.
4. oauthlib ships as a hard (non-extra) flet dependency
   (`oauthlib>=3.2.2; platform_system != "Emscripten"`), so it will always be
   present in the venv whether used or not. No action needed — just don't
   import it; pinning/upgrading is flet's business.

Scope note: the assignment mentions "flet publish/auth features" — verified
that only the **auth** half involves oauthlib. Flet's pubsub/publish path has
no oauthlib wiring (see §2 table).
