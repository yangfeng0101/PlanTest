# iOS Agent

Host-side helper for iOS real-device automation. Run this on the Mac that owns
Xcode, WebDriverAgent signing, connected iPhones, and the iOS Appium server.

Detailed local setup and troubleshooting: `../../docs/deployment/IOS_AGENT_SETUP.md`.

```bash
cd device-farm/services/ios-agent
python3 -m venv "${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv"
. "${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv/bin/activate"
pip install -r requirements.txt
IOS_APPIUM_HOST=http://127.0.0.1:4724 \
IOS_AGENT_PYTHON="$PWD/.venv/bin/python" \
IOS_XCODE_ORG_ID=TEAMID123 \
IOS_XCODE_SIGNING_ID="Apple Development" \
IOS_WDA_BUNDLE_ID=com.example.WebDriverAgentRunner \
IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true \
IOS_AGENT_AUTOMATION_READY_UDIDS=00000000-0000000000000000 \
uvicorn app:app --host 0.0.0.0 --port 8015
```

Docker services can then use `IOS_AGENT_URL=http://host.docker.internal:8015`
and `IOS_APPIUM_HOST=http://host.docker.internal:4724`.

For real-device WDA signing, pass the same values to `test-svc` and
`test-worker`:

- `IOS_XCODE_ORG_ID`: Apple Developer Team ID, for example `TEAMID123`
- `IOS_XCODE_SIGNING_ID`: signing identity, defaults to `Apple Development`
- `IOS_WDA_BUNDLE_ID`: unique WebDriverAgent bundle id, for example
  `com.example.WebDriverAgentRunner`
- `IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true`: lets Xcode pass
  `-allowProvisioningUpdates -allowProvisioningDeviceRegistration`

`/health` returns both `ok` for Agent process health and `ready` for Appium
reachability. `/devices` is conservative by default: `automation_ready` remains
false until WDA has been verified for that specific device. After a real-device
WDA smoke test succeeds, expose only those verified devices with:

```bash
IOS_AGENT_AUTOMATION_READY_UDIDS=00000000-0000000000000000,another-udid
```

Verified devices also expose static debug endpoints for the Device Farm screen
page:

- `GET /devices/{udid}/screenshot`
- `GET /devices/{udid}/source`
- `POST /devices/{udid}/stream-session`
- `DELETE /devices/{udid}/stream-session`
- `POST /devices/{udid}/tap`
- `POST /devices/{udid}/swipe`
- `POST /devices/{udid}/long-press`
- `POST /devices/{udid}/text`
- `POST /devices/{udid}/clear-text`
- `DELETE /devices/{udid}/debug-session`

These endpoints create cached Appium XCUITest sessions per UDID. `stream-session`
starts WDA/MJPEG for the experimental direct preview path in `screen-svc`; the
browser receives the MJPEG multipart stream directly, without LiveKit or H264
transcoding. Device Farm only exposes this preview when `device-svc` is started
with `IOS_ENABLE_EXPERIMENTAL_SCREEN=true` and `IOS_SCREEN_DRIVER=mjpeg-direct`.
Static screenshot/source/action endpoints remain the default iOS debugging path.
Continuous remote touch control is still not exposed; Device Farm keeps iOS
`remoteControl=false`.

The Device Farm UI uses static endpoints for optional 1s/2s/5s screenshot
refresh, UI hierarchy inspection, point tap, one-shot swipe, long press, text
input, and clear-text. Screenshot refresh can rebuild a broken WDA session once
before surfacing an error. Tap, swipe, and long-press coordinates use Appium/WDA
logical points. Text input and clear-text are sent to the currently focused
element after the user taps an input field.

Action endpoints accept `includeScreen` and default it to `false`. The
`mjpeg-direct` preview path keeps it disabled for lower latency because the
screen size is already known from stream preparation. Static screenshot
debugging can request `includeScreen=true` when it needs a fresh logical screen
snapshot. Action responses include `latency_ms`, `control_method`, and
`session_reused` for troubleshooting touch latency. Tap, swipe, and long-press
prefer direct WDA `/actions` for lower latency; if WDA direct control is not
available, the Agent falls back to Appium `mobile:` commands and then W3C
actions. Existing stream/debug sessions are reused without repeating device
enumeration or Appium status checks on every action.

WDA/MJPEG stream sessions use these optional environment variables:

- `IOS_AGENT_SESSION_CREATE_TIMEOUT`: Appium session creation timeout, default
  `90` seconds. First WDA startup can be slower than normal commands.
- `IOS_WDA_BASE_URL`: WDA HTTP endpoint for direct low-latency actions, default
  `http://127.0.0.1:8100`.
- `IOS_WDA_MJPEG_PORT_START` / `IOS_WDA_MJPEG_PORT_END`: port pool, default
  `9100-9199`
- `IOS_WDA_MJPEG_PUBLIC_HOST`: host seen by Docker `screen-svc`, default
  `host.docker.internal`
- `IOS_WDA_MJPEG_FRAMERATE`: default `20`
- `IOS_WDA_MJPEG_SCALING_FACTOR`: default `35`
- `IOS_WDA_MJPEG_QUALITY`: default `25`
