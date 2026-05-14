package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	screenauth "screen-svc/internal/auth"
	"screen-svc/internal/config"
	"screen-svc/internal/session"
)

func TestIOSMJPEGPrepareOccupiesAndStopReleasesDevice(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var occupied, released, agentStarted, agentStopped int

	deviceServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /api/v1/devices/ios-1":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":     "ios-1",
				"os":     "ios",
				"status": "online",
				"capabilities": map[string]any{
					"screen_mirror": true,
				},
			})
		case "POST /api/v1/devices/ios-1/occupy":
			occupied++
			w.WriteHeader(http.StatusOK)
		case "POST /api/v1/devices/ios-1/release":
			released++
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected device request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer deviceServer.Close()

	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "POST /devices/ios-1/stream-session":
			agentStarted++
			_ = json.NewEncoder(w).Encode(map[string]any{
				"device_id":  "ios-1",
				"session_id": "stream-1",
				"mjpeg_url":  "http://127.0.0.1:9999",
				"screen": map[string]any{
					"width":  390,
					"height": 844,
				},
			})
		case "DELETE /devices/ios-1/stream-session":
			agentStopped++
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected agent request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer agentServer.Close()

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig(deviceServer.URL, agentServer.URL))
	h.SetupRoutes(router)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/sessions/ios-1/ios-mjpeg/prepare", nil)
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("prepare status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if occupied != 1 || agentStarted != 1 {
		t.Fatalf("expected occupied=1 and agentStarted=1, got occupied=%d agentStarted=%d", occupied, agentStarted)
	}
	if !h.isIOSMJPEGActive("ios-1") {
		t.Fatalf("expected local iOS MJPEG session to be active")
	}

	req = httptest.NewRequest(http.MethodDelete, "/api/v1/sessions/ios-1/ios-mjpeg", nil)
	resp = httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("stop status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if released != 1 || agentStopped != 1 {
		t.Fatalf("expected released=1 and agentStopped=1, got released=%d agentStopped=%d", released, agentStopped)
	}
	if h.isIOSMJPEGActive("ios-1") {
		t.Fatalf("expected local iOS MJPEG session to be released")
	}
}

func TestIOSMJPEGPrepareRejectsBusyBeforeAgentCall(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var occupied, agentStarted int

	deviceServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /api/v1/devices/ios-1":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":     "ios-1",
				"os":     "ios",
				"status": "busy",
				"capabilities": map[string]any{
					"screen_mirror": true,
				},
			})
		case "POST /api/v1/devices/ios-1/occupy":
			occupied++
			w.WriteHeader(http.StatusBadRequest)
		default:
			t.Fatalf("unexpected device request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer deviceServer.Close()

	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		agentStarted++
		w.WriteHeader(http.StatusOK)
	}))
	defer agentServer.Close()

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig(deviceServer.URL, agentServer.URL))
	h.SetupRoutes(router)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/sessions/ios-1/ios-mjpeg/prepare", nil)
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusConflict {
		t.Fatalf("prepare status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if occupied != 0 || agentStarted != 0 {
		t.Fatalf("expected no occupy or agent call, got occupied=%d agentStarted=%d", occupied, agentStarted)
	}
}

func TestIOSMJPEGPrepareTimeoutReleasesStaleLease(t *testing.T) {
	gin.SetMode(gin.TestMode)
	oldTimeout := iosMJPEGPrepareAttachTimeout
	iosMJPEGPrepareAttachTimeout = 20 * time.Millisecond
	defer func() { iosMJPEGPrepareAttachTimeout = oldTimeout }()

	var released, agentStopped int
	deviceServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /api/v1/devices/ios-1":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":          "ios-1",
				"os":          "ios",
				"status":      "busy",
				"occupied_by": "anonymous",
				"capabilities": map[string]any{
					"screen_mirror": true,
				},
			})
		case "POST /api/v1/devices/ios-1/release":
			released++
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected device request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer deviceServer.Close()

	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "DELETE /devices/ios-1/stream-session":
			agentStopped++
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected agent request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer agentServer.Close()

	h := NewHandler(session.NewManager(), testConfig(deviceServer.URL, agentServer.URL))
	user := &screenauth.User{ID: "anonymous", Role: "admin"}
	h.deviceLeaseByID["ios-1"] = "anonymous"
	h.iosMJPEGByDevice["ios-1"] = "anonymous"

	h.scheduleIOSMJPEGPrepareCleanup("ios-1", user)
	time.Sleep(80 * time.Millisecond)

	if h.isIOSMJPEGActive("ios-1") {
		t.Fatalf("expected stale iOS MJPEG session to be cleared")
	}
	if released != 1 || agentStopped != 1 {
		t.Fatalf("expected released=1 and agentStopped=1, got released=%d agentStopped=%d", released, agentStopped)
	}
}

func TestIOSMJPEGDebugActionProxiesThroughActiveStream(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var agentCalled int

	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/devices/ios-1/swipe" {
			t.Fatalf("unexpected agent request %s %s", r.Method, r.URL.Path)
		}
		agentCalled++
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Fatalf("decode agent payload: %v", err)
		}
		if payload["includeScreen"] != false {
			t.Fatalf("expected includeScreen=false, got %#v", payload["includeScreen"])
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"success":        true,
			"latency_ms":     123,
			"control_method": "mobile: dragFromToForDuration",
		})
	}))
	defer agentServer.Close()

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig("http://127.0.0.1:1", agentServer.URL))
	h.iosMJPEGByDevice["ios-1"] = "anonymous"
	h.SetupRoutes(router)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/sessions/ios-1/ios-mjpeg/debug/swipe",
		strings.NewReader(`{"startX":10,"startY":20,"endX":30,"endY":40,"includeScreen":false}`),
	)
	req.Header.Set("Content-Type", "application/json")
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("debug action status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if agentCalled != 1 {
		t.Fatalf("expected one agent call, got %d", agentCalled)
	}

	var data map[string]any
	if err := json.Unmarshal(resp.Body.Bytes(), &data); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if data["success"] != true || data["control_method"] != "mobile: dragFromToForDuration" {
		t.Fatalf("unexpected response: %#v", data)
	}
}

func TestIOSMJPEGDebugActionRequiresActiveStream(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var agentCalled int
	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		agentCalled++
		w.WriteHeader(http.StatusOK)
	}))
	defer agentServer.Close()

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig("http://127.0.0.1:1", agentServer.URL))
	h.SetupRoutes(router)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/sessions/ios-1/ios-mjpeg/debug/tap", strings.NewReader(`{"x":10,"y":20}`))
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusConflict {
		t.Fatalf("debug action status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if agentCalled != 0 {
		t.Fatalf("expected no agent call, got %d", agentCalled)
	}
}

func TestGetSessionReportsActiveIOSMJPEGStream(t *testing.T) {
	gin.SetMode(gin.TestMode)

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig("http://127.0.0.1:1", "http://127.0.0.1:2"))
	h.iosMJPEGByDevice["ios-1"] = "anonymous"
	h.SetupRoutes(router)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/sessions/ios-1", nil)
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("session status = %d, body = %s", resp.Code, resp.Body.String())
	}
	var data map[string]any
	if err := json.Unmarshal(resp.Body.Bytes(), &data); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if data["active"] != true || data["mode"] != "ios-mjpeg" {
		t.Fatalf("expected active iOS MJPEG session, got %#v", data)
	}
}

func TestIOSMJPEGUIHierarchyProxiesThroughActiveStream(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var agentCalled int

	agentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/devices/ios-1/source" {
			t.Fatalf("unexpected agent request %s %s", r.Method, r.URL.Path)
		}
		agentCalled++
		_ = json.NewEncoder(w).Encode(map[string]any{
			"device_id": "ios-1",
			"source": `<AppiumAUT type="XCUIElementTypeApplication" x="0" y="0" width="390" height="844" enabled="true" visible="true">
  <XCUIElementTypeWindow type="XCUIElementTypeWindow" x="0" y="0" width="390" height="844" enabled="true" visible="true">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="Settings" label="Settings" x="20" y="40" width="80" height="40" enabled="true" visible="true" accessible="true"/>
  </XCUIElementTypeWindow>
</AppiumAUT>`,
		})
	}))
	defer agentServer.Close()

	router := gin.New()
	h := NewHandler(session.NewManager(), testConfig("http://127.0.0.1:1", agentServer.URL))
	h.iosMJPEGByDevice["ios-1"] = "anonymous"
	h.SetupRoutes(router)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/sessions/ios-1/ios-mjpeg/ui-hierarchy", nil)
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("ui hierarchy status = %d, body = %s", resp.Code, resp.Body.String())
	}
	if agentCalled != 1 {
		t.Fatalf("expected one agent call, got %d", agentCalled)
	}
	var data map[string]any
	if err := json.Unmarshal(resp.Body.Bytes(), &data); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if data["platform"] != "ios" {
		t.Fatalf("expected platform ios, got %#v", data["platform"])
	}
	elements, ok := data["elements"].([]any)
	if !ok || len(elements) != 2 {
		t.Fatalf("expected two parsed elements, got %#v", data["elements"])
	}
	button := elements[1].(map[string]any)
	if button["text"] != "Settings" || button["content_desc"] != "Settings" {
		t.Fatalf("unexpected button element: %#v", button)
	}
}

func TestReleaseTrackedDeviceLeaseSkipsDifferentOwner(t *testing.T) {
	var released int
	deviceServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /api/v1/devices/ios-1":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":          "ios-1",
				"os":          "ios",
				"status":      "busy",
				"occupied_by": "test-svc",
				"capabilities": map[string]any{
					"screen_mirror": true,
				},
			})
		case "POST /api/v1/devices/ios-1/release":
			released++
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected device request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer deviceServer.Close()

	h := NewHandler(session.NewManager(), testConfig(deviceServer.URL, "http://127.0.0.1:1"))
	h.deviceLeaseByID["ios-1"] = "screen-user"

	if h.releaseTrackedDeviceLease(nil, "ios-1") {
		t.Fatalf("expected release to be skipped for a different owner")
	}
	if released != 0 {
		t.Fatalf("expected release endpoint not to be called, got %d calls", released)
	}
}

func testConfig(deviceURL, iosAgentURL string) *config.Config {
	return &config.Config{
		Device: config.DeviceConfig{ServiceURL: deviceURL},
		IOSAgent: config.IOSAgentConfig{
			URL: iosAgentURL,
		},
		Auth: config.AuthConfig{
			Enabled: false,
		},
		LiveKit: config.LiveKitConfig{
			APIKey:    "devkey",
			APISecret: "secret",
			PublicURL: "ws://localhost:7880",
		},
	}
}
