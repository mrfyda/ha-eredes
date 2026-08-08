# `Authorization-Request` carries a reCAPTCHA token, and sending the `aat` there is load-bearing

The client sends the access token in **both** the `Cookie` header and the
`Authorization-Request` header. Despite its name, `Authorization-Request` is the
portal's reCAPTCHA slot, not an authorization header — but it must be present or the
request is refused. Do not "clean this up".

## Context

The portal's Angular `AuthRecaptchaInterceptor` sets the header on every outbound
request from a reCAPTCHA v3 token, never from a credential:

```js
intercept(n, i) {
  return this.recaptchaV3Service.execute("AuthRecaptchaInterceptor").pipe(
    qe(a => i.handle(n.clone({ headers: this.getUserAgent(n, a) }))), …
// getUserAgent → n.headers.set("Authorization-Request", i)   // i = the v3 token
```

On a `403`, it re-runs the request with a v2 challenge token plus `recaptcha-v2: true`.
So a browser puts a Google captcha token in this header; this integration puts a JWT
there. That reads like a bug — and it is semantically wrong — but the gateway guarding
`/ms/*` only checks that the header is **present** on data endpoints. It never validates
the value. Removing it breaks everything.

Measured against a live token on `POST /ms/reading/data-usage/edm/get` (2026-08-08):

| Request | Result |
|---|---|
| `Cookie: aat=…` only | **`403` + `recaptcha: true`** |
| `Cookie: aat=…` + `Authorization-Request: <aat>` | **`200` + data** |
| `Authorization: Bearer <aat>` only | `403` + `recaptcha: true` |
| `Authorization: Bearer <aat>` + `Authorization-Request: <aat>` | **`200` + data** |
| `Authorization-Request: <aat>`, no cookie, no bearer | `401` |

Two things follow. The bot gate and the credential check are **independent**: the last
row reaches the auth layer and fails there, so a present header satisfies the gate
regardless of the credential. And the credential itself may travel as either the `aat`
cookie or a Bearer token — the data endpoint accepts both.

An attempt to remove the header as a tidy-up was caught only by testing it against a
live token; it would have taken the integration from working to permanently `403`.

## Considered Options

- **Drop `Authorization-Request`, keep the cookie** — rejected. Proven to yield `403`.
- **Send a real reCAPTCHA v3 token** — rejected. Minting one requires executing Google's
  JS in a browser with the site key, which is the arms race this project avoids
  (see [0001](0001-manual-token-paste-auth.md)).
- **Keep sending the `aat` in both places** — chosen. It satisfies the gate, costs
  nothing, and leaks no more than the cookie already does.

## Consequences

`403` and `401` mean different things and must not be collapsed:

- **`401`** — the credential is dead. Correct to raise `ConfigEntryAuthFailed` and ask
  the user for a fresh token.
- **`403` with a `recaptcha` response header** — the gateway wants a challenge solved.
  This says nothing about the token, which is very likely still valid. Treating it as an
  auth failure sends the user to copy a token that would change nothing. It should be a
  transient failure that retries.

The current `get_consumption` raises `ERedesAuthenticationError` for both, so a bot
challenge surfaces to the user as *"Authentication failed - please update your access
token"*. That is a real defect, though **not** the cause of the routine ~2h expiry
reported in [0001](0001-manual-token-paste-auth.md) — that one is the 91-minute token.
