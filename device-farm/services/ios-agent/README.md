# iOS Agent

Host-side helper for iOS real-device automation. Run this on the Mac that owns
Xcode, WebDriverAgent signing, connected iPhones, and the iOS Appium server.

```bash
cd device-farm/services/ios-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
IOS_APPIUM_HOST=http://127.0.0.1:4724 uvicorn app:app --host 0.0.0.0 --port 8015
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
