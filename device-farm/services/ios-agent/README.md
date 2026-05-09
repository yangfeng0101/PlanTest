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
- `POST /devices/{udid}/tap`
- `POST /devices/{udid}/swipe`
- `POST /devices/{udid}/long-press`
- `POST /devices/{udid}/text`
- `POST /devices/{udid}/clear-text`
- `DELETE /devices/{udid}/debug-session`

These endpoints create a cached Appium XCUITest debug session per UDID. They do
not provide realtime screen streaming or continuous remote touch control. Tap,
swipe, and long-press coordinates use Appium/WDA logical points. Text input and
clear-text are sent to the currently focused element after the user taps an
input field.
