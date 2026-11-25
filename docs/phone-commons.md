# Popit Springboard: phone chat and secure voice

## Final URLs

The process prints these at startup:

- **Phone Springboard, secure (chat + microphone):**
  **https://<popit-lan-ip>:5210/phone.html**
- **Same Springboard on plain HTTP (read-only):**
  **http://<popit-lan-ip>:5209/phone.html**
- **Certificate download for the phone:**
  **https://<popit-lan-ip>:5210/popit-cert.cer**
  (The old `/popit-cert.pem` URL is kept as an alias and serves the same DER
  certificate with an installable `.cer` filename.)
- **Desktop toast:** `http://127.0.0.1:5207/`
- Certificate files: `runlogs/toast/phone-cert.pem` and `runlogs/toast/phone-key.pem`.
  The certificate has `IP:<popit-lan-ip>`, `DNS:popit.local`, and `DNS:localhost` SANs.
  If the LAN address changes, delete both files and restart `toast.py`; it generates a
  new certificate for the current address.

```bash
python toast.py
# popit phone https://<popit-lan-ip>:5210/phone.html
# popit certificate https://<popit-lan-ip>:5210/popit-cert.cer
```

On Windows, allow Python on the **private** network if Windows Firewall asks. The
surface is same-network only. The HTTPS listener is `--https-port` (default `5210`); it can
be disabled with `--no-https`, and the LAN surface with `--no-lan`.

## Accept the certificate on the phone

The certificate is locally generated, not a public CA certificate. A browser must accept
it for the page to be a secure context; `getUserMedia` is unavailable on the plain HTTP
LAN URL.

### iOS / iPadOS (Safari)

1. Open **https://<popit-lan-ip>:5210/phone.html** and choose **Advanced → Proceed** if Safari
   shows the certificate warning.
2. For full trust (and reliable PWA/microphone permission), open
   **https://<popit-lan-ip>:5210/popit-cert.cer**, allow the profile download, then install it
   in **Settings → General → VPN & Device Management**. The `.pem` URL serves the same
   DER certificate if an older bookmark is used.
3. Open **Settings → General → About → Certificate Trust Settings**, enable full trust for
   the Popit certificate.
4. Reload the Springboard. Use **Share → Add to Home Screen** for the standalone Popit app.

### Android (Chrome)

1. Open **https://<popit-lan-ip>:5210/phone.html**, then **Advanced → Proceed** at the warning.
2. To install the CA, open **https://<popit-lan-ip>:5210/popit-cert.cer**; then use
   **Settings → Security → Encryption & credentials → Install a certificate → CA certificate**
   and select the downloaded file. Android labels this as a user certificate.
3. Reload, allow the microphone prompt, and use **Chrome menu → Add to Home screen**.

The plain HTTP address remains available for read-only viewing. Its Springboard marks
itself **READ ONLY** and disables the composer and voice controls; no owner mutation or
audio upload is accepted by the phone API over HTTP.

## Springboard

The home grid is the family surface: **Commons**, **Voice Call**, and a tile for every live
agent lane. Tapping **Commons** opens the all-lanes conversation; tapping an agent opens
that lane and narrows the next owner turn to it. **Voice Call** uses the same secure origin,
captures microphone audio in the browser, and posts a WAV to the local Whisper pipeline.
The home diamond, the browser back gesture, and a right swipe return home.

The owner composer posts through **`POST /api/toast/phone/hear`**. The voice view posts a
WAV through **`POST /api/toast/phone/audio?lane=...`**. Both land in the same
`runlogs/toast/archive.jsonl` as the desktop and use the normal agent dispatch. A recognized
phone phrase goes through the same quiet-mic owner guards as the desktop microphone.

## Civilian desk (retired)

`/civilians.html` is retired, and the Springboard no longer carries a Civilians tile: its
tiles are the live lanes and its own voice surface. The assistant, driver and civilian
buttons beside the desktop voice controls are retired as well, because they described a
lane relationship the family does not have.

The C9 needs, the feeling-wheel identity, the typed Choice/Noul/Score decisions and the
seven-field contract are still recorded and still read at `/api/toast/civilians`, written
through `POST /api/toast/civilian/name`. A call that includes a contract is grounded in that
contract; a lane with a low C9 need is asked to name care before accepting new work. The
record and its evidence are in [`civilians.md`](civilians.md).

## Standalone call client

The contact-book and MCP-calling page is published separately at
**https://alacripose.github.io/popit-call/**. Its local companion is:

```sh
cd call-client
python serve.py --port 5220 --bridge http://127.0.0.1:5207
# open http://127.0.0.1:5220/
```

GitHub Pages serves only the static client. A remote caller must use the host's HTTPS
surface or the companion; signing and trust are documented in
[`../call-client/ENVELOPE.md`](../call-client/ENVELOPE.md). The client's **Signed package**
field sends a `popit.call-envelope/1` package to `/api/toast/call/join`; the host checks the
Ed25519 signature, the BLAKE3 trust registry, the 15-minute window and the single-use nonce.

## Reproduction

### 1. Phone owner text reaches the archive and draws a reply

```bash
curl -k -X POST https://<popit-lan-ip>:5210/api/toast/phone/hear \
  -H 'Content-Type: application/json' \
  -d '{"text":"Phone chat proof from the Springboard.","lane":"Whisper"}'

curl -k https://<popit-lan-ip>:5210/api/toast
# The user row has targets ["Whisper"]; the following cua row has role "Whisper"
# and question equal to the text above.
```

### 2. Captured phone audio reaches the voice pipeline

Generate a deterministic test WAV (the same PCM WAV shape the browser sends) and post it:

```powershell
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile("F:\Documents\popit-shell\runlogs\toast\phone-voice-proof.wav")
$s.Speak("This is a phone voice proof from the Springboard.")
$s.Dispose()
```

```bash
curl -k --data-binary @runlogs/toast/phone-voice-proof.wav \
  -H 'Content-Type: audio/wav' \
  'https://<popit-lan-ip>:5210/api/toast/phone/audio?lane=Whisper'
# {"ok":true,"transcript":"This is a phone voice proof from the springboard.", ...}
```

The endpoint writes a temporary WAV, runs `tools/transcribe_wav.py` (Whisper-tiny.en,
16 kHz mono), removes the temp file, and calls the owner voice path. Agent replies are
written into the shared archive exactly like a desktop turn.

### 3. Quiet-mic sign-off is still caught and repaired

```powershell
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile("F:\Documents\popit-shell\runlogs\toast\quiet-signoff.wav")
$s.Speak("Thank you for watching. Thank you for watching.")
$s.Dispose()
```

```bash
curl -k --data-binary @runlogs/toast/quiet-signoff.wav \
  -H 'Content-Type: audio/wav' \
  'https://<popit-lan-ip>:5210/api/toast/phone/audio?lane=Whisper'
# The transcript is recognized, but no kind=user row is created.
# A repair event is written and the phrase is hidden from live state.
```

`archive.repair_hallucinations()` still scans existing owner rows and cua rows whose
`question` was that owner row, and persists their keys in
`runlogs/toast/archive-quarantine.json`. `archive.add` refuses a new hallucinated
`kind="user"` row, so a quiet sign-off cannot enter the conversation in the first place.

### 4. Basic transport checks

```bash
python -m py_compile toast.py archive.py voice.py mind_bridge.py tools/mic_whisper.py tools/transcribe_wav.py
node --check ui/phone.js
node --check ui/phone-sw.js
python -m json.tool ui/phone-manifest.webmanifest
curl -k -I https://<popit-lan-ip>:5210/phone.html
curl -k https://<popit-lan-ip>:5210/phone-manifest.webmanifest
curl -k https://<popit-lan-ip>:5210/popit-cert.cer
```

Server stdout/stderr are written to `runlogs/toast/live.stdout.log` and
`runlogs/toast/live.stderr.log` when launched with redirection as shown in the runbook
below. Expected client disconnects (`ConnectionResetError`, broken pipes, TLS EOF) are
ignored; other server errors still print a traceback.

## Runbook

```bash
python toast.py
```

or, to keep the logs for inspection:

```powershell
Start-Process -FilePath "pythonw.exe" -ArgumentList "toast.py" `
  -WorkingDirectory "F:\Documents\popit-shell" -WindowStyle Hidden `
  -RedirectStandardOutput "F:\Documents\popit-shell\runlogs\toast\live.stdout.log" `
  -RedirectStandardError "F:\Documents\popit-shell\runlogs\toast\live.stderr.log"
```

The mobile shell is `/phone.html`; the desktop Vite-free surface remains `/toast.html`.
The phone surface is intentionally a separate view so the Qt toast does not become a
touch-first launcher.
