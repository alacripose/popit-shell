# 2026-11-24 — secure LAN phone path, cold client proof

Target: a phone that has never visited Popit before must get the working
Springboard from `https://<popit-lan-ip>:5210/phone.html`, with the same certificate
the user is told to install, and the cert download must install on iPhone or
Android.

## What changed

- `/popit-cert.pem` was serving PEM as `application/x-pem-file`. That is not the
  install prompt iOS Safari expects and is awkward for Android’s CA installer.
- `toast.py` now converts the live `runlogs/toast/phone-cert.pem` to DER in memory
  and serves that DER at both `/popit-cert.cer` and the old `/popit-cert.pem`
  alias with:
  - `Content-Type: application/x-x509-ca-cert`
  - `Content-Disposition: attachment; filename="popit-cert.cer"`
  - `X-Content-Type-Options: nosniff`
- `send_body()` accepts an optional download filename; no cert or key is copied
  into the web root.
- The phone’s voice screen links to `/popit-cert.cer`.
- `phone-sw.js` cache was bumped to `popit-springboard-v3` so an older installed
  shell does not keep the old hint.
- `tools/toast_probe.py` now carries `phone-cert-installable`, which fails unless
  the served download is DER (`0x30`) with the CA MIME type.
- Docs and startup output now name `/popit-cert.cer`; the `.pem` URL remains a
  documented alias for the same DER body.

## Live ownership

Exactly one process owns the phone ports after the restart:

```text
127.0.0.1:5207 LISTENING 19208
<popit-lan-ip>:5208 LISTENING 19208
<popit-lan-ip>:5209 LISTENING 19208
<popit-lan-ip>:5210 LISTENING 19208
```

## Cold page

Fetched with a fresh client (no cookie jar, no redirect, `--noproxy '*'`,
`--no-sessionid`) from the LAN origin:

```text
GET https://<popit-lan-ip>:5210/phone.html
HTTP/1.0 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 6920
Cache-Control: no-store
sha256 717c26dff98cfade9be5d512ee0e9271baf8cadf3a69b232a9a7a2508acc33cd
```

The served bytes contain `id="voice-screen"`, `id="voice-start"`,
`id="voice-stop"`, `id="secure-pill"`, `id="call-sheet"`, `/phone.js`,
`/phone-calls.js`, and `/phone.css`. They contain no `http://`, `ws://`,
`127.0.0.1` or `localhost` reference.

Every referenced asset was fetched on the TLS listener:

```text
/phone.css                  200 text/css
/phone.js                   200 text/javascript
/phone-calls.js             200 text/javascript
/contour.js                 200 text/javascript
/contour.json               200 application/json
/phone-manifest.webmanifest 200 application/manifest+json
/phone-sw.js                200 text/javascript  (popit-springboard-v3)
/popit-icon-512.png         200 image/png
/popit-icon.svg             200 image/svg+xml
```

The cold Edge render used a fresh profile and the test-only
`--ignore-certificate-errors` flag (there is no phone trust store on this PC):

```text
data-secure="true"
SECURE VOICE
CERT-COVERED
HTTPS · MIC READY
```

No `READ ONLY` or `HTTP · VIEW ONLY` marker appeared. A real phone with the
installed certificate is the remaining trust test; see “Not verified” below.

## Certificate

Downloaded from both the canonical URL and the old alias:

```text
GET https://<popit-lan-ip>:5210/popit-cert.cer
HTTP/1.0 200 OK
Content-Type: application/x-x509-ca-cert
Content-Length: 826
Content-Disposition: attachment; filename="popit-cert.cer"
X-Content-Type-Options: nosniff

file: Certificate, Version=3
subject=CN=<popit-lan-ip>
issuer=CN=<popit-lan-ip>
X509v3 Subject Alternative Name:
    IP Address:<popit-lan-ip>, DNS:popit.local, DNS:localhost
X509v3 Basic Constraints: critical
    CA:TRUE
sha256 AB:6F:12:AD:6F:94:34:A5:F8:0A:98:03:ED:A5:FD:34:BE:E4:88:88:DC:A3:37:E4:1E:ED:BF:8D:A8:89:04:06
```

The same fingerprint came from:

- the local `runlogs/toast/phone-cert.pem`;
- the downloaded `/popit-cert.cer` body;
- the certificate presented by `openssl s_client` on `<popit-lan-ip>:5210`.

The downloaded DER was turned into a fresh PEM trust anchor and verified:

```text
openssl verify -CAfile proof-cert.pem proof-cert.pem
proof-cert.pem: OK

curl --cacert proof-cert.pem https://<popit-lan-ip>:5210/phone.html
200 6920
sha256 717c26dff98cfade9be5d512ee0e9271baf8cadf3a69b232a9a7a2508acc33cd
```

`/popit-cert.pem` returned the same 826-byte DER body, same CA MIME type and same
fingerprint.

## Page endpoints over TLS

The phone has no WebSocket. It uses same-origin SSE (`/api/toast/events`) and
same-origin HTTPS POSTs for signaling.

```text
GET  /api/toast                         200  (mic listening, external 0, open 1)
GET  /api/toast/external/contacts       200
GET  /api/toast/external/incoming       200
POST /api/toast/lanes                   200
POST /api/toast/phone/hear              200  (empty body => empty-text)
POST /api/toast/phone/audio             400  (empty body => audio-size)
GET  /api/toast/events                  200  text/event-stream
POST /api/toast/external/call/answer    409  (TLS handler reached)
POST /api/toast/external/call/state     409  (TLS handler reached)
POST /api/toast/external/call/ice       409  (TLS handler reached)
POST /api/toast/external/call/end       409  (TLS handler reached)
```

The secure routes reject the plain LAN listener:

```text
POST http://<popit-lan-ip>:5209/api/toast/phone/hear   403 secure-origin-required
POST http://<popit-lan-ip>:5209/api/toast/phone/audio  403 secure-origin-required
POST http://<popit-lan-ip>:5209/api/toast/external/call/answer 403 secure-origin-required
```

## Gates

```text
python -m py_compile toast.py external_agents.py envelope.py tools/external_agent.py tools/toast_probe.py  # 0
node --check ui/phone.js; ui/phone-calls.js; ui/phone-sw.js                                                 # 0 each
python tools/gate.py                                                                                        # 25 checks, 0 refusals
python tools/toast_probe.py                                                                                 # 47 passed, 5 failed
```

The five probe failures are the pre-existing unrelated toast UI drift checks:
`voice-profiles`, `workspace-and-heard-present`, `participant-glyphs`,
`addressing-all`, `no-text-inputs`. The new `phone-cert-installable` check passed.

## Not verified

- No physical iPhone or Android was available in this run. The actual Safari
  warning/Profile Downloaded flow and Android CA installer UI were not observed.
- The cold Edge render used `--ignore-certificate-errors`; it proves the served
  page’s secure JS state over the real TLS origin, not that a phone has installed
  and trusted the CA. The cert trust path itself was proven with `openssl verify`
  and a fresh `curl --cacert` request.
- No real phone microphone capture or real WebRTC call was made in this run.
  The audio route was reached with an empty body; the signaling routes were
  reached over TLS with invalid bodies. `tools/toast_probe.py` separately covers
  the external enrollment/call signaling surface with synthetic SDP.
