package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"

	"screen-svc/internal/ios"
	"screen-svc/internal/scrcpy"
	webrtcmgr "screen-svc/internal/webrtc"
)

// DeviceType represents the type of device
type DeviceType string

const (
	DeviceTypeAndroid DeviceType = "android"
	DeviceTypeIOS     DeviceType = "ios"
)

// ScreenSession represents an active screen mirroring session
type ScreenSession struct {
	DeviceID      string
	DeviceType    DeviceType
	Scrcpy        *scrcpy.Process
	IOSMirror     *ios.IOSMirror
	WebRTC        *webrtcmgr.Manager
	Clients       map[*websocket.Conn]bool
	ScreenWidth   int
	ScreenHeight  int
	VideoWidth    int
	VideoHeight   int
	CreatedAt     string
	ctx           context.Context
	cancel        context.CancelFunc
}

// ScreenManager manages all screen mirroring sessions
type ScreenManager struct {
	sessions     map[string]*ScreenSession
	mu           sync.RWMutex
	config       *scrcpy.Config
	iosConfig    *ios.Config
	iceServers   []webrtcmgr.ICEServer
	logger       *logrus.Logger
}

// NewScreenManager creates a new screen manager
func NewScreenManager(config *scrcpy.Config, iosConfig *ios.Config, iceServers []webrtcmgr.ICEServer) *ScreenManager {
	if iosConfig == nil {
		iosConfig = ios.DefaultConfig()
	}
	return &ScreenManager{
		sessions:   make(map[string]*ScreenSession),
		config:     config,
		iosConfig:  iosConfig,
		iceServers: iceServers,
		logger:     logrus.New(),
	}
}

// detectDeviceType determines device type from device ID
// iOS devices have UDID format (40 hex chars), Android uses serial numbers
func detectDeviceType(deviceID string) DeviceType {
	// iOS UDID is typically 40 hex characters
	// Android serial numbers vary in length and format
	if len(deviceID) == 40 {
		allHex := true
		for _, c := range deviceID {
			if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
				allHex = false
				break
			}
		}
		if allHex {
			return DeviceTypeIOS
		}
	}
	// Check if device ID starts with common iOS prefixes
	if strings.HasPrefix(strings.ToLower(deviceID), "000080") {
		return DeviceTypeIOS
	}
	return DeviceTypeAndroid
}

// StartSession starts a new screen session
func (m *ScreenManager) StartSession(deviceID string) (*ScreenSession, error) {
	return m.StartSessionWithType(deviceID, detectDeviceType(deviceID))
}

// StartSessionWithType starts a new screen session with explicit device type
func (m *ScreenManager) StartSessionWithType(deviceID string, deviceType DeviceType) (*ScreenSession, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check if session already exists
	if session, exists := m.sessions[deviceID]; exists {
		return session, nil
	}

	// Create context for cancellation
	ctx, cancel := context.WithCancel(context.Background())

	var session *ScreenSession
	var err error

	switch deviceType {
	case DeviceTypeIOS:
		session, err = m.startIOSSession(ctx, cancel, deviceID)
	default:
		session, err = m.startAndroidSession(ctx, cancel, deviceID)
	}

	if err != nil {
		cancel()
		return nil, err
	}

	m.sessions[deviceID] = session
	return session, nil
}

// startAndroidSession starts a screen session for an Android device
func (m *ScreenManager) startAndroidSession(ctx context.Context, cancel context.CancelFunc, deviceID string) (*ScreenSession, error) {
	// Create scrcpy process
	process := scrcpy.NewProcess(deviceID, m.config)
	if err := process.Start(); err != nil {
		return nil, fmt.Errorf("failed to start scrcpy: %w", err)
	}

	// Get screen dimensions
	width, height, err := process.GetScreenSize()
	if err != nil {
		m.logger.Warnf("Failed to get screen size for %s: %v", deviceID, err)
		width, height = 1080, 1920 // default
	}

	// Create WebRTC manager
	webrtcManager := webrtcmgr.NewManager(
		webrtcmgr.WithICEServers(m.iceServers),
		webrtcmgr.WithICEPortRange(40000, 50000),
	)

	session := &ScreenSession{
		DeviceID:   deviceID,
		DeviceType: DeviceTypeAndroid,
		Scrcpy:     process,
		WebRTC:     webrtcManager,
		Clients:    make(map[*websocket.Conn]bool),
		ScreenWidth:  width,
		ScreenHeight: height,
		CreatedAt:  "now",
		ctx:        ctx,
		cancel:     cancel,
	}

	// Start video stream goroutine
	go m.streamVideo(ctx, session)

	return session, nil
}

// startIOSSession starts a screen session for an iOS device
func (m *ScreenManager) startIOSSession(ctx context.Context, cancel context.CancelFunc, deviceID string) (*ScreenSession, error) {
	// Create iOS mirror
	iosMirror := ios.NewIOSMirror(deviceID, m.iosConfig,
		ios.WithLogger(m.logger),
	)

	if err := iosMirror.Start(); err != nil {
		return nil, fmt.Errorf("failed to start iOS mirror: %w", err)
	}

	// Get screen dimensions (may be detected on first frame)
	width, height := iosMirror.GetScreenSize()
	if width == 0 || height == 0 {
		width, height = 1170, 2532 // Default iPhone resolution
	}

	// Create WebRTC manager
	webrtcManager := webrtcmgr.NewManager(
		webrtcmgr.WithICEServers(m.iceServers),
		webrtcmgr.WithICEPortRange(40000, 50000),
	)

	session := &ScreenSession{
		DeviceID:   deviceID,
		DeviceType: DeviceTypeIOS,
		IOSMirror:  iosMirror,
		WebRTC:     webrtcManager,
		Clients:    make(map[*websocket.Conn]bool),
		ScreenWidth:  width,
		ScreenHeight: height,
		CreatedAt:  "now",
		ctx:        ctx,
		cancel:     cancel,
	}

	// Start video stream goroutine for iOS
	go m.streamIOSVideo(ctx, session)

	return session, nil
}

// StopSession stops a screen session
func (m *ScreenManager) StopSession(deviceID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	session, exists := m.sessions[deviceID]
	if !exists {
		return fmt.Errorf("session not found")
	}

	// Cancel the context
	if session.cancel != nil {
		session.cancel()
	}

	// Stop device-specific mirroring
	if session.DeviceType == DeviceTypeIOS && session.IOSMirror != nil {
		if err := session.IOSMirror.Stop(); err != nil {
			m.logger.Warnf("Error stopping iOS mirror: %v", err)
		}
	} else if session.Scrcpy != nil {
		if err := session.Scrcpy.Stop(); err != nil {
			m.logger.Warnf("Error stopping scrcpy: %v", err)
		}
	}

	// Close all websocket connections
	for conn := range session.Clients {
		conn.Close()
	}

	// Close WebRTC
	session.WebRTC.Close()

	delete(m.sessions, deviceID)
	return nil
}

// GetSession returns a session by device ID
func (m *ScreenManager) GetSession(deviceID string) (*ScreenSession, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	session, exists := m.sessions[deviceID]
	if !exists {
		return nil, fmt.Errorf("session not found")
	}

	return session, nil
}

// ListSessions lists all active sessions
func (m *ScreenManager) ListSessions() []map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var sessions []map[string]interface{}
	for id, session := range m.sessions {
		sessions = append(sessions, map[string]interface{}{
			"device_id":     id,
			"device_type":   session.DeviceType,
			"client_count":  len(session.Clients),
			"screen_width":  session.ScreenWidth,
			"screen_height": session.ScreenHeight,
			"created_at":    session.CreatedAt,
		})
	}
	return sessions
}

// RegisterWebsocket registers a websocket connection
func (m *ScreenManager) RegisterWebsocket(deviceID string, conn *websocket.Conn) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	session, exists := m.sessions[deviceID]
	if !exists {
		return fmt.Errorf("session not found - start session first")
	}

	session.Clients[conn] = true
	m.logger.Infof("Client registered for device %s", deviceID)
	return nil
}

// UnregisterWebsocket unregisters a websocket connection
func (m *ScreenManager) UnregisterWebsocket(deviceID string, conn *websocket.Conn) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if session, exists := m.sessions[deviceID]; exists {
		delete(session.Clients, conn)
		m.logger.Infof("Client unregistered for device %s", deviceID)
	}
}

// HandleControlMessage handles incoming control messages
func (m *ScreenManager) HandleControlMessage(deviceID string, data []byte) {
	var msg map[string]interface{}
	if err := json.Unmarshal(data, &msg); err != nil {
		m.logger.Warnf("Failed to parse control message: %v", err)
		return
	}

	msgType, ok := msg["type"].(string)
	if !ok {
		return
	}

	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		m.logger.Warnf("Session not found for %s", deviceID)
		return
	}

	// Route to device-specific handler
	switch session.DeviceType {
	case DeviceTypeIOS:
		m.handleIOSControlMessage(session, msgType, msg)
	default:
		m.handleAndroidControlMessage(session, msgType, msg)
	}
}

// handleAndroidControlMessage handles control messages for Android devices
func (m *ScreenManager) handleAndroidControlMessage(session *ScreenSession, msgType string, msg map[string]interface{}) {
	if session.Scrcpy == nil {
		m.logger.Warnf("Scrcpy not initialized for %s", session.DeviceID)
		return
	}

	switch msgType {
	case "touch":
		m.handleTouchMessage(session, msg)
	case "key":
		m.handleKeyMessage(session, msg)
	case "text":
		m.handleTextMessage(session, msg)
	case "scroll":
		m.handleScrollMessage(session, msg)
	case "back":
		session.Scrcpy.SendBack()
	case "home":
		session.Scrcpy.SendHome()
	case "rotate":
		session.Scrcpy.SendRotate()
	}
}

// handleIOSControlMessage handles control messages for iOS devices
func (m *ScreenManager) handleIOSControlMessage(session *ScreenSession, msgType string, msg map[string]interface{}) {
	if session.IOSMirror == nil {
		m.logger.Warnf("iOS mirror not initialized for %s", session.DeviceID)
		return
	}

	switch msgType {
	case "touch":
		xVal, ok := msg["x"].(float64)
		if !ok {
			return
		}
		yVal, ok := msg["y"].(float64)
		if !ok {
			return
		}
		action, _ := msg["action"].(string)
		var actionByte byte
		switch action {
		case "down":
			actionByte = 0
		case "up":
			actionByte = 1
		default:
			actionByte = 0
		}
		if err := session.IOSMirror.SendTouch(int(xVal), int(yVal), actionByte); err != nil {
			m.logger.Warnf("Failed to send iOS touch: %v", err)
		}
	case "swipe":
		x1Val, _ := msg["x1"].(float64)
		y1Val, _ := msg["y1"].(float64)
		x2Val, _ := msg["x2"].(float64)
		y2Val, _ := msg["y2"].(float64)
		if err := session.IOSMirror.SendSwipe(int(x1Val), int(y1Val), int(x2Val), int(y2Val)); err != nil {
			m.logger.Warnf("Failed to send iOS swipe: %v", err)
		}
	case "home":
		if err := session.IOSMirror.SendHome(); err != nil {
			m.logger.Warnf("Failed to send iOS home: %v", err)
		}
	}
}

func (m *ScreenManager) handleTouchMessage(session *ScreenSession, msg map[string]interface{}) {
	xVal, ok := msg["x"].(float64)
	if !ok {
		m.logger.Warnf("Invalid or missing x coordinate")
		return
	}
	yVal, ok := msg["y"].(float64)
	if !ok {
		m.logger.Warnf("Invalid or missing y coordinate")
		return
	}
	action, _ := msg["action"].(string)

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.ActionDown
	case "up":
		actionByte = scrcpy.ActionUp
	case "move":
		actionByte = scrcpy.ActionMove
	default:
		actionByte = scrcpy.ActionDown
	}

	x := int(xVal)
	y := int(yVal)

	if err := session.Scrcpy.SendTouch(x, y, actionByte, session.ScreenWidth, session.ScreenHeight); err != nil {
		m.logger.Warnf("Failed to send touch: %v", err)
	}
}

func (m *ScreenManager) handleKeyMessage(session *ScreenSession, msg map[string]interface{}) {
	keyCodeVal, ok := msg["keyCode"].(float64)
	if !ok {
		m.logger.Warnf("Invalid or missing keyCode")
		return
	}
	action, _ := msg["action"].(string)

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.KeyActionDown
	case "up":
		actionByte = scrcpy.KeyActionUp
	default:
		actionByte = scrcpy.KeyActionDown
	}

	if err := session.Scrcpy.SendKey(int(keyCodeVal), actionByte); err != nil {
		m.logger.Warnf("Failed to send key: %v", err)
	}
}

func (m *ScreenManager) handleTextMessage(session *ScreenSession, msg map[string]interface{}) {
	text, ok := msg["text"].(string)
	if !ok {
		m.logger.Warnf("Invalid or missing text")
		return
	}

	if err := session.Scrcpy.SendText(text); err != nil {
		m.logger.Warnf("Failed to send text: %v", err)
	}
}

func (m *ScreenManager) handleScrollMessage(session *ScreenSession, msg map[string]interface{}) {
	xVal, _ := msg["x"].(float64)
	yVal, _ := msg["y"].(float64)
	dxVal, _ := msg["dx"].(float64)
	dyVal, _ := msg["dy"].(float64)

	if err := session.Scrcpy.SendScroll(int(xVal), int(yVal), int(dxVal), int(dyVal), session.ScreenWidth, session.ScreenHeight); err != nil {
		m.logger.Warnf("Failed to send scroll: %v", err)
	}
}

// HandleWebRTCSignaling handles WebRTC signaling over WebSocket
func (m *ScreenManager) HandleWebRTCSignaling(deviceID string, conn *websocket.Conn) {
	// Start session if not exists
	if _, err := m.StartSession(deviceID); err != nil {
		m.logger.Errorf("Failed to start session for %s: %v", deviceID, err)
		conn.Close()
		return
	}

	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		conn.Close()
		return
	}

	// Use the signaling handler from webrtc package
	handler := webrtcmgr.NewSignalingHandler(session.WebRTC, conn)
	handler.Handle()
}

// SendTouch sends touch event
func (m *ScreenManager) SendTouch(deviceID string, x, y int, action string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// Handle iOS devices
	if session.DeviceType == DeviceTypeIOS && session.IOSMirror != nil {
		var actionByte byte
		switch action {
		case "down":
			actionByte = 0
		case "up":
			actionByte = 1
		default:
			actionByte = 0
		}
		return session.IOSMirror.SendTouch(x, y, actionByte)
	}

	// Handle Android devices
	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.ActionDown
	case "up":
		actionByte = scrcpy.ActionUp
	case "move":
		actionByte = scrcpy.ActionMove
	default:
		actionByte = scrcpy.ActionDown
	}

	return session.Scrcpy.SendTouch(x, y, actionByte, session.ScreenWidth, session.ScreenHeight)
}

// SendKeyEvent sends key event
func (m *ScreenManager) SendKeyEvent(deviceID string, keyCode int, action string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// iOS doesn't support key events the same way
	if session.DeviceType == DeviceTypeIOS {
		return fmt.Errorf("key events not supported for iOS devices")
	}

	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.KeyActionDown
	case "up":
		actionByte = scrcpy.KeyActionUp
	default:
		actionByte = scrcpy.KeyActionDown
	}

	return session.Scrcpy.SendKey(keyCode, actionByte)
}

// SendText sends text input
func (m *ScreenManager) SendText(deviceID string, text string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// iOS text input would go through WDA
	if session.DeviceType == DeviceTypeIOS {
		return fmt.Errorf("text input not implemented for iOS")
	}

	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	return session.Scrcpy.SendText(text)
}

// SendBack sends back key
func (m *ScreenManager) SendBack(deviceID string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// iOS doesn't have a back button
	if session.DeviceType == DeviceTypeIOS {
		return fmt.Errorf("back button not available on iOS")
	}

	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	return session.Scrcpy.SendBack()
}

// SendHome sends home key
func (m *ScreenManager) SendHome(deviceID string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// Handle iOS devices
	if session.DeviceType == DeviceTypeIOS && session.IOSMirror != nil {
		return session.IOSMirror.SendHome()
	}

	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	// HOME is keycode 3
	return session.Scrcpy.SendHome()
}

// SendRotate rotates the device screen
func (m *ScreenManager) SendRotate(deviceID string) error {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("session not found")
	}

	// iOS rotation not implemented
	if session.DeviceType == DeviceTypeIOS {
		return fmt.Errorf("rotation not implemented for iOS")
	}

	if session.Scrcpy == nil {
		return fmt.Errorf("scrcpy not initialized")
	}

	return session.Scrcpy.SendRotateDevice()
}

func (m *ScreenManager) streamVideo(ctx context.Context, session *ScreenSession) {
	buf := make([]byte, 65536)
	frameCount := 0

	m.logger.Infof("Starting Android video stream for device %s", session.DeviceID)

	for {
		select {
		case <-ctx.Done():
			m.logger.Infof("Video stream stopped for %s", session.DeviceID)
			return
		default:
			n, err := session.Scrcpy.Read(buf)
			if err != nil {
				m.logger.Warnf("Video stream ended for %s: %v", session.DeviceID, err)
				return
			}

			// Forward to WebRTC
			if err := session.WebRTC.SendVideo(buf[:n]); err != nil {
				m.logger.Warnf("Failed to send video for %s: %v", session.DeviceID, err)
			}

			frameCount++

			// Log progress periodically
			if frameCount%300 == 0 {
				m.logger.Debugf("Device %s: streamed %d frames", session.DeviceID, frameCount)
			}
		}
	}
}

// streamIOSVideo handles video streaming for iOS devices
// iOS uses PNG/MJPEG screenshots that need to be converted to H.264
func (m *ScreenManager) streamIOSVideo(ctx context.Context, session *ScreenSession) {
	buf := make([]byte, 65536)
	frameCount := 0

	m.logger.Infof("Starting iOS video stream for device %s", session.DeviceID)

	for {
		select {
		case <-ctx.Done():
			m.logger.Infof("iOS video stream stopped for %s", session.DeviceID)
			return
		default:
			if session.IOSMirror == nil {
				m.logger.Warnf("iOS mirror not initialized")
				return
			}

			n, err := session.IOSMirror.Read(buf)
			if err != nil {
				m.logger.Debugf("iOS frame read: %v", err)
				continue
			}

			if n == 0 {
				continue
			}

			// Forward to WebRTC
			// Note: iOS sends PNG/MJPEG frames, not H.264
			// For MVP, we send raw frames - ideally should convert to H.264
			if err := session.WebRTC.SendVideo(buf[:n]); err != nil {
				m.logger.Warnf("Failed to send iOS video for %s: %v", session.DeviceID, err)
			}

			frameCount++

			// Update screen size if detected
			if session.ScreenWidth == 0 || session.ScreenHeight == 0 {
				w, h := session.IOSMirror.GetScreenSize()
				if w > 0 && h > 0 {
					session.ScreenWidth = w
					session.ScreenHeight = h
					m.logger.Infof("Updated iOS screen size: %dx%d", w, h)
				}
			}

			// Log progress periodically
			if frameCount%100 == 0 {
				m.logger.Debugf("iOS Device %s: streamed %d frames", session.DeviceID, frameCount)
			}
		}
	}
}
