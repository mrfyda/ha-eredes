# Authentication is a manually-pasted access token

E-REDES login is protected by Google reCAPTCHA Enterprise, so an `aat` access token
cannot be minted programmatically — users copy it from their browser and paste it into
the integration by hand. The API never re-issues the `aat` (it only rolls a secondary
`PHPSESSID` cookie via `Set-Cookie`), so the token also cannot be refreshed from
responses; when it expires, Home Assistant triggers the reauth flow and the user pastes
a fresh one.

## Considered Options

- **Scripted login** — rejected: defeating reCAPTCHA Enterprise is brittle, a moving
  target, and a Terms-of-Service risk.
- **Refresh the token from response cookies** — rejected as impossible: inspection of a
  live `edm/get` response confirmed only `PHPSESSID` appears in `Set-Cookie`; the `aat`
  is never returned, and it is the primary authenticator (a bare `aat` authorizes on
  its own — `PHPSESSID` is secondary). So `aat` expiry is a hard ceiling.

See `CONTEXT.md` (Authentication) for the access-token / server-session distinction.
