package session

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/pion/webrtc/v3"
	"github.com/sirupsen/logrus"

	"screen-svc/internal/config"
	"screen-svc/internal/scrcpy"
	"screen-svc/internal/webrtc"
)

// Session represents an active screen mirroring session
type Session struct {
	DeviceID     string
	Scrcpy       *scrcpy.Process
	WebRTC       *webrtc.Manager
	Clients      map[*websocket.Conn]*ClientInfo
	ScreenWidth  int
	ScreenHeight int
	VideoWidth   int
	VideoHeight  int
	CreatedAt    time.Time
	Stats        *SessionStats
	ctx          context.Context
	cancel       context.CancelFunc
	mu           sync.RWMutex
}

// ClientInfo holds information about a connected client
type ClientInfo struct {
	ConnectedAt time.Time
	IsSignaling bool // True if this is a WebRTC signaling connection
}

// SessionStats holds session statistics
type SessionStats struct {
	FrameCount   uint64
	BytesSent    uint64
	LastFrameAt  time.Time
	Errors       uint64
}

// Manager manages all screen mirroring sessions
type Manager struct {
	sessions   map[string]*Session
	mu         sync.RWMutex
	config     *config.Config
	scrcpyCfg  *scrcpy.Config
	iceServers []webrtc.ICEServer
	logger     *logrus.Logger
}

// NewManager creates a new session manager
func NewManager(cfg *config.Config) *Manager {
	// Build scrcpy config
	scrcpyCfg := &scrcpy.Config{
		MaxResolution: cfg.Scrcpy.MaxResolution,
		MaxFPS:        cfg.Scrcpy.MaxFPS,
		BitRate:       cfg.Scrcpy.BitRate,
		Codec:         cfg.Scrcpy.Codec,
		ScrcpyPath:    "scrcpy", // Can be overridden via env
		ADBPath:       "adb",
	}

	// Build ICE servers
	iceServers := make([]webrtc.ICEServer, 0, len(cfg.WebRTC.ICEServers))
	for _, server := range cfg.WebRTC.ICEServers {
		iceServers = append(iceServers, webrtc.ICEServer{
			URLs: server.URLs,
		})
	}
	if len(iceServers) == 0 {
		iceServers = []webrtc.ICEServer{
			{URLs: []string{"stun:stun.l.google.com:19302"}},
		}
	}

	return &Manager{
		sessions:   make(map[string]*Session),
		config:     cfg,
		scrcpyCfg:  scrcpyCfg,
		iceServers: iceServers,
		logger:     logrus.New(),
	}
}

// StartSession starts a new screen session for a device
func (m *Manager) StartSession(deviceID string) (*Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check if session already exists
	if session, exists := m.sessions[deviceID]; exists {
		m.logger.Infof("Session already exists for device %s", deviceID)
		return session, nil
	}

	// Create context for cancellation
	ctx, cancel := context.WithCancel(context.Background())

	// Create scrcpy process
	process := scrcpy.NewProcess(deviceID, m.scrcpyCfg,
		scrcpy.WithLogger(m.logger),
	)

	if err := process.Start(); err != nil {
		cancel()
		return nil, fmt.Errorf("failed to start scrcpy: %w", err)
	}

	// Create WebRTC manager with ICE configuration
	webrtcManager := webrtc.NewManager(
		webrtc.WithICEServers(m.iceServers),
		webrtc.WithICEPortRange(uint16(m.config.WebRTC.MinPort), uint16(m.config.WebRTC.MaxPort)),
		webrtc.WithLogger(m.logger),
	)

	// Get screen dimensions
	screenW, screenH := process.GetScreenSize()
	// Video dimensions are calculated during process start based on max resolution
	videoW, videoH := screenW, screenH

	session := &Session{
		DeviceID:     deviceID,
		Scrcpy:       process,
		WebRTC:       webrtcManager,
		Clients:      make(map[*websocket.Conn]*ClientInfo),
		ScreenWidth:  screenW,
		ScreenHeight: screenH,
		VideoWidth:   videoW,
		VideoHeight:  videoH,
		CreatedAt:    time.Now(),
		Stats:        &SessionStats{},
		ctx:          ctx,
		cancel:       cancel,
	}

	m.sessions[deviceID] = session

	// Start video stream goroutine
	go m.streamVideo(ctx, session)

	m.logger.Infof("Session started for device %s (screen: %dx%d, video: %dx%d)",
		deviceID, screenW, screenH, videoW, videoH)

	return session, nil
}

// StopSession stops a screen session
func (m *Manager) StopSession(deviceID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	session, exists := m.sessions[deviceID]
	if !exists {
		return fmt.Errorf("session not found for device %s", deviceID)
	}

	// Cancel context to stop video stream
	if session.cancel != nil {
		session.cancel()
	}

	// Stop scrcpy process
	if err := session.Scrcpy.Stop(); err != nil {
		m.logger.Warnf("Error stopping scrcpy for %s: %v", deviceID, err)
	}

	// Close WebRTC connection
	if err := session.WebRTC.Close(); err != nil {
		m.logger.Warnf("Error closing WebRTC for %s: %v", deviceID, err)
	}

	// Close all websocket connections
	for conn := range session.Clients {
		conn.Close()
	}

	delete(m.sessions, deviceID)
	m.logger.Infof("Session stopped for device %s", deviceID)
	return nil
}

// GetSession returns a session by device ID
func (m *Manager) GetSession(deviceID string) (*Session, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	session, exists := m.sessions[deviceID]
	if !exists {
		return nil, fmt.Errorf("session not found for device %s", deviceID)
	}
	return session, nil
}

// ListSessions lists all active sessions
func (m *Manager) ListSessions() []map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	sessions := make([]map[string]interface{}, 0, len(m.sessions))
	for id, session := range m.sessions {
		session.mu.RLock()
		sessions = append(sessions, map[string]interface{}{
			"device_id":     id,
			"client_count":  len(session.Clients),
			"screen_width":  session.ScreenWidth,
			"screen_height": session.ScreenHeight,
			"video_width":   session.VideoWidth,
			"video_height":  session.VideoHeight,
			"created_at":    session.CreatedAt,
			"frame_count":   session.Stats.FrameCount,
			"bytes_sent":    session.Stats.BytesSent,
		})
		session.mu.RUnlock()
	}
	return sessions
}

// RegisterClient registers a websocket client with a session
func (m *Manager) RegisterClient(deviceID string, conn *websocket.Conn, isSignaling bool) error {
	session, err := m.getOrCreateSession(deviceID)
	if err != nil {
		return err
	}

	session.mu.Lock()
	defer session.mu.Unlock()

	session.Clients[conn] = &ClientInfo{
		ConnectedAt: time.Now(),
		IsSignaling: isSignaling,
	}

	m.logger.Infof("Client connected to device %s (signaling: %v)", deviceID, isSignaling)
	return nil
}

// UnregisterClient unregisters a websocket client
func (m *Manager) UnregisterClient(deviceID string, conn *websocket.Conn) {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if !exists {
		return
	}

	session.mu.Lock()
	defer session.mu.Unlock()

	delete(session.Clients, conn)
	m.logger.Infof("Client disconnected from device %s", deviceID)
}

// HandleControlMessage handles incoming control messages from clients
func (m *Manager) HandleControlMessage(deviceID string, data []byte) error {
	session, err := m.GetSession(deviceID)
	if err != nil {
		return err
	}

	var msg map[string]interface{}
	if err := json.Unmarshal(data, &msg); err != nil {
		return fmt.Errorf("failed to parse control message: %w", err)
	}

	msgType, ok := msg["type"].(string)
	if !ok {
		return fmt.Errorf("missing message type")
	}

	switch msgType {
	case "touch":
		return m.handleTouch(session, msg)
	case "key":
		return m.handleKey(session, msg)
	case "text":
		return m.handleText(session, msg)
	case "scroll":
		return m.handleScroll(session, msg)
	case "back":
		return session.Scrcpy.SendBack()
	case "home":
		return session.Scrcpy.SendHome()
	case "power":
		return session.Scrcpy.SendPower()
	case "menu":
		return session.Scrcpy.SendMenu()
	case "rotate":
		return session.Scrcpy.SendRotateDevice()
	default:
		return fmt.Errorf("unknown message type: %s", msgType)
	}
}

func (m *Manager) handleTouch(session *Session, msg map[string]interface{}) error {
	x := int(msg["x"].(float64))
	y := int(msg["y"].(float64))
	action := msg["action"].(string)

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.ActionDown
	case "up":
		actionByte = scrcpy.ActionUp
	default:
		actionByte = scrcpy.ActionMove
	}

	return session.Scrcpy.SendTouch(x, y, actionByte, session.ScreenWidth, session.ScreenHeight)
}

func (m *Manager) handleKey(session *Session, msg map[string]interface{}) error {
	keyCode := int(msg["keyCode"].(float64))
	action := msg["action"].(string)

	var actionByte byte
	switch action {
	case "down":
		actionByte = scrcpy.KeyActionDown
	default:
		actionByte = scrcpy.KeyActionUp
	}

	return session.Scrcpy.SendKey(keyCode, actionByte)
}

func (m *Manager) handleText(session *Session, msg map[string]interface{}) error {
	text, ok := msg["text"].(string)
	if !ok {
		return fmt.Errorf("missing text")
	}
	return session.Scrcpy.SendText(text)
}

func (m *Manager) handleScroll(session *Session, msg map[string]interface{}) error {
	x := int(msg["x"].(float64))
	y := int(msg["y"].(float64))
	dx := int(msg["dx"].(float64))
	dy := int(msg["dy"].(float64))
	return session.Scrcpy.SendScroll(x, y, dx, dy, session.ScreenWidth, session.ScreenHeight)
}

// HandleWebRTCSignaling handles WebRTC signaling over WebSocket
func (m *Manager) HandleWebRTCSignaling(deviceID string, conn *websocket.Conn) error {
	session, err := m.getOrCreateSession(deviceID)
	if err != nil {
		return err
	}

	handler := webrtc.NewSignalingHandler(session.WebRTC, conn)
	return handler.Handle()
}

// getOrCreateSession gets existing session or creates a new one
func (m *Manager) getOrCreateSession(deviceID string) (*Session, error) {
	m.mu.RLock()
	session, exists := m.sessions[deviceID]
	m.mu.RUnlock()

	if exists {
		return session, nil
	}

	return m.StartSession(deviceID)
}

// streamVideo streams video from scrcpy to WebRTC
func (m *Manager) streamVideo(ctx context.Context, session *Session) {
	buf := make([]byte, 65536) // 64KB buffer

	for {
		select {
		case <-ctx.Done():
			m.logger.Infof("Video stream stopped for %s", session.DeviceID)
			return
		default:
		}

		if !session.Scrcpy.IsRunning() {
			m.logger.Warnf("Scrcpy process not running for %s", session.DeviceID)
			return
		}

		n, err := session.Scrcpy.Read(buf)
		if err != nil {
			m.logger.Warnf("Video read error for %s: %v", session.DeviceID, err)
			session.mu.Lock()
			session.Stats.Errors++
			session.mu.Unlock()
			continue
		}

		if n == 0 {
			continue
		}

		// Forward to WebRTC
		if err := session.WebRTC.SendVideo(buf[:n]); err != nil {
			m.logger.Warnf("WebRTC send error for %s: %v", session.DeviceID, err)
		}

		// Update stats
		session.mu.Lock()
		session.Stats.FrameCount++
		session.Stats.BytesSent += uint64(n)
		session.Stats.LastFrameAt = time.Now()
		session.mu.Unlock()
	}
}
