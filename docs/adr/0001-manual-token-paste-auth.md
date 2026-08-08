# Authentication is a manually-pasted access token

E-REDES login is protected by Google reCAPTCHA, so an `aat` access token cannot be
minted programmatically — users copy it from their browser and paste it into the
integration by hand. The token cannot be renewed either, so when it expires Home
Assistant triggers the reauth flow and the user pastes a fresh one.

## Context

The original version of this ADR asserted the above from partial evidence: it had only
inspected `Set-Cookie` on `edm/get` responses. A full investigation on 2026-08-08,
against a live token, confirmed the conclusion but corrected two of its premises (see
**Corrections** below) and pinned the numbers.

### The access token lives 91 minutes

Decoding a freshly minted `aat` (`iss: msauth-jwt`, `roles: [RESIDENTIAL]`):

```
iat 1786177376   2026-08-08T08:22:56Z
exp 1786182836   2026-08-08T09:53:56Z
    lifetime     1:31:00  = 5460s
```

91 minutes, as a hard `exp` claim — the 90-minute `PHPSESSID` window (`Max-Age=5400`)
plus 60 seconds. With `DEFAULT_SCAN_INTERVAL` at one hour, a pasted token survives
roughly two polls. **The integration is arithmetically guaranteed to fail about two
hours after every paste.** This is not an intermittent bug.

### Nothing renews the token

Every candidate was tried with a live `aat`. Only `PHPSESSID` is ever rolled; the `aat`
is never re-issued:

| Endpoint | Result |
|---|---|
| `GET /session` | `200 {"token": true}` — validates, does not renew |
| `GET /`, `/consumptions/history`, `/dashboard` | `200` — PHP app rolls `PHPSESSID` only |
| `POST/GET /ms/auth/auth/token-check` | `403` + `recaptcha: true` |
| `POST/GET /ms/auth/reserved-area-token` | `403` + `recaptcha: true` |

The renewal endpoints exist but sit behind the bot gate. `token-check` also takes a
token argument (`tokenCheck({token})`), so it validates email-link tokens rather than
refreshing a session. There is no refresh token anywhere in the flow.

### Login is genuinely captcha-validated

`POST /ms/auth/auth/signin` returns `403` + `recaptcha: true` for every variant tried:
with and without `Authorization-Request`, and with `User-Agent-Context` of `WEB`, `APP`
and `MOBILE`, and an okhttp user-agent. Unlike the data endpoints (see
[0003](0003-authorization-request-is-the-recaptcha-slot.md)), signin validates a real
reCAPTCHA token rather than merely checking a header is present.

## Considered Options

- **Scripted login** — rejected. Defeating reCAPTCHA is brittle, a moving target, a
  Terms-of-Service risk, and squarely an arms race. `rf-santos/eredes-scraper` tried it
  with Playwright + stealth; its own code detects the "Validação de Segurança" modal and
  gives up with *"Captcha detected. Try again later"*.
- **Refresh the token from response cookies** — rejected as impossible, per the table
  above.
- **Harvest a live browser session** — rejected. The portal signs users out after
  roughly the token's lifetime, so there is no long-lived browser session to read; a
  headless browser beside Home Assistant would have to re-run the captcha-gated login
  about 16 times a day.
- **Reverse the mobile app's API** — rejected: there is no mobile API. `pt.eredes.digital.app`
  v1.0.9 is a Capacitor shell whose entire `assets/public/main.js` does
  `window.location = 'https://balcaodigital.e-redes.pt/?app&v=109'`. Its `classes.dex`
  contains no E-REDES URLs and no credential-storage plugin, so it authenticates through
  the same captcha-gated web signin inside a WebView. The `accessTokenMobile`
  querystring hook in the web bundle is a vestige of a predecessor app.
- **Official consumer API** — unavailable. The E-REDES developer portal publishes only
  grid-infrastructure and outage products; there is no Portuguese equivalent of Spain's
  Datadis.

## Corrections to the original ADR

- *"a bare `aat` authorizes on its own"* — **false**. A cookie-only request is refused
  with `403` + `recaptcha: true`. The `Authorization-Request` header must also be
  present. See [0003](0003-authorization-request-is-the-recaptcha-slot.md).
- *"the `aat` is the primary authenticator"* — imprecise. The bot gate is checked
  independently of the credential, and the credential may travel as either the `aat`
  cookie or an `Authorization: Bearer` token.

## Consequences

A 91-minute, human-minted credential cannot support a polling integration. Since E-REDES
publishes consumption with a ~24h delay, the token is best treated as a **one-shot batch
credential**: on each paste, backfill everything since the last import, then stop
expecting scheduled polls to succeed. The README must not imply that re-authentication
is automatic.
