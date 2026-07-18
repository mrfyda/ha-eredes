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
The JWT credential minted at login and the **primary** authenticator — a bare `aat`,
with no other cookies, authorizes an API call on its own. Has a fixed lifetime and is
**not** re-issued in responses, so it cannot be refreshed without logging in again.
_Avoid_: "session cookie", bare "token" (both are ambiguous — see below).

**Server session (`PHPSESSID`)**:
A **secondary** cookie the server issues and rolls on every response (90-minute
sliding window). It rides along with requests and is bootstrapped even from a
bare-`aat` first call, but it is not the primary authenticator — keeping it fresh does
not extend access past the access token's expiry.
_Avoid_: bare "session" (collides with the aiohttp HTTP client session).

**Login**:
The interactive, browser-based sign-in that mints an `aat`. It is protected by Google
reCAPTCHA Enterprise and therefore cannot be automated — the reason the `aat` is pasted
in by hand rather than obtained programmatically.
