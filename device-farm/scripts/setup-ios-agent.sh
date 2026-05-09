#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="$ROOT_DIR/services/ios-agent"
DEFAULT_VENV_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv"
VENV_DIR="${IOS_AGENT_VENV:-$DEFAULT_VENV_DIR}"
IOS_AGENT_HOST="${IOS_AGENT_HOST:-0.0.0.0}"
IOS_AGENT_PORT="${IOS_AGENT_PORT:-8015}"
IOS_APPIUM_HOST_LOCAL="${IOS_APPIUM_HOST:-http://127.0.0.1:${IOS_APPIUM_PORT:-4724}}"
IOS_APPIUM_PORT="${IOS_APPIUM_PORT:-4724}"
LOG_DIR="${IOS_AGENT_LOG_DIR:-$ROOT_DIR/.logs}"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
APPIUM_LABEL="com.devicefarm.appium-ios"
IOS_AGENT_LABEL="com.devicefarm.ios-agent"
APPIUM_PLIST="$LAUNCH_AGENT_DIR/$APPIUM_LABEL.plist"
IOS_AGENT_PLIST="$LAUNCH_AGENT_DIR/$IOS_AGENT_LABEL.plist"

info() {
  printf '[ios-agent-setup] %s\n' "$*"
}

warn() {
  printf '[ios-agent-setup] WARN: %s\n' "$*" >&2
}

if [[ ! -d "$SERVICE_DIR" ]]; then
  warn "iOS Agent service directory not found: $SERVICE_DIR"
  exit 1
fi

info "Checking Xcode"
if ! command -v xcodebuild >/dev/null 2>&1; then
  warn "xcodebuild not found. Install full Xcode and run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
else
  xcodebuild -version || true
fi

if ! xcode-select -p 2>/dev/null | grep -q "/Applications/Xcode.app"; then
  warn "xcode-select does not point to full Xcode. Recommended: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
fi

info "Preparing Python virtualenv: $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$SERVICE_DIR/requirements.txt"

if command -v appium >/dev/null 2>&1; then
  info "Checking Appium XCUITest driver"
  if ! appium driver list --installed 2>/dev/null | grep -qi "xcuitest"; then
    warn "Appium XCUITest driver is not installed. Run: appium driver install xcuitest"
  fi
else
  warn "appium command not found. Run: npm install -g appium && appium driver install xcuitest"
fi

cat <<EOF

Next manual commands:
  appium --address 127.0.0.1 --port $IOS_APPIUM_PORT --base-path /

  cd "$SERVICE_DIR"
  IOS_AGENT_PYTHON="$VENV_DIR/bin/python" IOS_APPIUM_HOST=$IOS_APPIUM_HOST_LOCAL "$VENV_DIR/bin/python" -m uvicorn app:app --host $IOS_AGENT_HOST --port $IOS_AGENT_PORT

Docker env:
  IOS_AGENT_URL=http://host.docker.internal:$IOS_AGENT_PORT
  IOS_APPIUM_HOST=http://host.docker.internal:$IOS_APPIUM_PORT
  IOS_XCODE_ORG_ID=<apple-team-id>
  IOS_XCODE_SIGNING_ID=Apple Development
  IOS_WDA_BUNDLE_ID=<unique-wda-bundle-id>
  IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true

EOF

if [[ "${INSTALL_LAUNCH_AGENTS:-false}" != "true" ]]; then
  info "Set INSTALL_LAUNCH_AGENTS=true to generate LaunchAgent plists."
  exit 0
fi

if [[ -z "${IOS_AGENT_AUTOMATION_READY_UDIDS:-}" ]]; then
  warn "IOS_AGENT_AUTOMATION_READY_UDIDS is empty. iOS devices will stay automation_ready=false until verified UDIDs are configured."
fi

APPIUM_BIN="$(command -v appium || true)"
if [[ -z "$APPIUM_BIN" ]]; then
  warn "Cannot generate Appium LaunchAgent because appium command was not found."
  exit 1
fi

mkdir -p "$LAUNCH_AGENT_DIR" "$LOG_DIR"

info "Writing LaunchAgent: $APPIUM_PLIST"
cat > "$APPIUM_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$APPIUM_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APPIUM_BIN</string>
    <string>--address</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>$IOS_APPIUM_PORT</string>
    <string>--base-path</string>
    <string>/</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/appium-ios.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/appium-ios.err.log</string>
</dict>
</plist>
PLIST

info "Writing LaunchAgent: $IOS_AGENT_PLIST"
cat > "$IOS_AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$IOS_AGENT_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV_DIR/bin/python</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>app:app</string>
    <string>--host</string>
    <string>$IOS_AGENT_HOST</string>
    <string>--port</string>
    <string>$IOS_AGENT_PORT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$SERVICE_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>IOS_APPIUM_HOST</key>
    <string>$IOS_APPIUM_HOST_LOCAL</string>
    <key>IOS_AGENT_PYTHON</key>
    <string>$VENV_DIR/bin/python</string>
    <key>IOS_AGENT_AUTOMATION_READY_UDIDS</key>
    <string>${IOS_AGENT_AUTOMATION_READY_UDIDS:-}</string>
    <key>IOS_XCODE_ORG_ID</key>
    <string>${IOS_XCODE_ORG_ID:-}</string>
    <key>IOS_XCODE_SIGNING_ID</key>
    <string>${IOS_XCODE_SIGNING_ID:-}</string>
    <key>IOS_WDA_BUNDLE_ID</key>
    <string>${IOS_WDA_BUNDLE_ID:-}</string>
    <key>IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION</key>
    <string>${IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION:-}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/ios-agent.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/ios-agent.err.log</string>
</dict>
</plist>
PLIST

if [[ "${START_LAUNCH_AGENTS:-false}" == "true" ]]; then
  info "Loading LaunchAgents"
  launchctl bootout "gui/$(id -u)" "$APPIUM_PLIST" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)" "$IOS_AGENT_PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$APPIUM_PLIST"
  launchctl bootstrap "gui/$(id -u)" "$IOS_AGENT_PLIST"
  launchctl kickstart -k "gui/$(id -u)/$APPIUM_LABEL"
  launchctl kickstart -k "gui/$(id -u)/$IOS_AGENT_LABEL"
else
  cat <<EOF
LaunchAgents were generated. Start them with:
  launchctl bootstrap "gui/\$(id -u)" "$APPIUM_PLIST"
  launchctl bootstrap "gui/\$(id -u)" "$IOS_AGENT_PLIST"
  launchctl kickstart -k "gui/\$(id -u)/$APPIUM_LABEL"
  launchctl kickstart -k "gui/\$(id -u)/$IOS_AGENT_LABEL"
EOF
fi

info "Done"
