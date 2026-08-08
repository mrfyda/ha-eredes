# E-REDES Integration

A Home Assistant custom integration that fetches electricity consumption from the
E-REDES Balcão Digital portal. This glossary fixes the vocabulary of two areas that
are easy to confuse: the **metering domain** (what the data represents) and the
**authentication model** (how requests are credentialed).

## Metering

**CPE**:
The identifier of a single electricity delivery point (*Código de Ponto de Entrega*),
e.g. `PT0002000012345678AB`. One configured meter corresponds to one CPE.
_Avoid_: "meter id" (the meter and the delivery point are distinct — see **Meter**).

**Meter**:
The physical metering device serving a CPE, identified by its serial number
(`meterReaderSerialNumber`). Reported as a `utilitiesDevice` in API responses.

**Register**:
A metering channel identified by an energy-flow code. `A+` is active energy
**imported** from the grid (consumption); `A-` is active energy **exported** to the
grid (injection, e.g. rooftop solar). The integration currently reads only `A+`.
_Avoid_: "channel", "direction".

**Load curve**:
The time series of energy per fixed 15-minute interval for one register, as returned
by the `edm/get` endpoint (`meterLoadCurves` → `loadCurves`).

**Reading**:
A single load-curve point — the energy consumed (or exported) during one 15-minute
interval. Carries an optional `meterLoadCurveStatus` data-quality flag.
_Avoid_: "measurement", "sample".

## Authentication

**Access token (`aat`)**:
The JWT credential minted at login. Carries a hard `exp` claim **91 minutes** after
issue, and is **never** re-issued — not by `/session`, not by page loads, not by the
portal's own `token-check` or `reserved-area-token` endpoints. It therefore cannot be
refreshed without logging in again. Travels in the `Cookie` header; the data endpoint
equally accepts it as `Authorization: Bearer`.
_Avoid_: "session cookie", bare "token" (both are ambiguous — see below).

**Bot gate (`Authorization-Request`)**:
A header the portal fills with a **reCAPTCHA token**, checked independently of the
credential. On `/ms/*` data endpoints the gateway only verifies the header is
*present*, so this integration passes the `aat` there; on signin it validates a real
token, which is why login cannot be automated. A request carrying a valid credential
but no `Authorization-Request` is refused with `403` and a `recaptcha: true` response
header. See `docs/adr/0003`.
_Avoid_: reading the name as "authorization" — it authorizes nothing.

**Server session (`PHPSESSID`)**:
A **secondary** cookie the server issues and rolls on every response (90-minute
sliding window). It rides along with requests and is bootstrapped even from a
bare-`aat` first call, but it is not a credential — keeping it fresh does not extend
access past the access token's expiry.
_Avoid_: bare "session" (collides with the aiohttp HTTP client session).

**Login**:
The interactive, browser-based sign-in that mints an `aat`. Protected by Google
reCAPTCHA and therefore not automatable — the reason the `aat` is pasted in by hand.
The E-REDES mobile app offers no way around this: it is a Capacitor shell that loads
this same web portal in a WebView (see `docs/adr/0001`).
