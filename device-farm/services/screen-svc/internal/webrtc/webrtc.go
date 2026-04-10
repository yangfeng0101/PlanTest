package webrtc

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v3"
	"github.com/sirupsen/logrus"

	"screen-svc/internal/video"
)

// Manager manages WebRTC connections
type Manager struct {
	peerConnection *webrtc.PeerConnection
	videoTrack     *webrtc.TrackLocalStaticSample
	rtpPacker      *video.RTPPacker
	nalParser      *video.NALParser
	logger         *logrus.Logger
	mu             sync.Mutex
	onICECandidate func(*webrtc.ICECandidate)
	frameCount     uint32
	startTime      time.Time
	iceServers     []webrtc.ICEServer
	icePorts       PortRange
}

// PortRange defines the range of ports to use for ICE
type PortRange struct {
	Min uint16
	Max uint16
}

// ICEServer is an alias for webrtc.ICEServer for external use
type ICEServer = webrtc.ICEServer

// ManagerOption is a functional option for Manager
type ManagerOption func(*Manager)

// WithICEServers sets the ICE servers for the manager
func WithICEServers(servers []webrtc.ICEServer) ManagerOption {
	return func(m *Manager) {
		m.iceServers = servers
	}
}

// WithICEPortRange sets the ICE port range
func WithICEPortRange(min, max uint16) ManagerOption {
	return func(m *Manager) {
		m.icePorts = PortRange{Min: min, Max: max}
	}
}

// WithLogger sets the logger
func WithLogger(logger *logrus.Logger) ManagerOption {
	return func(m *Manager) {
		m.logger = logger
	}
}

// NewManager creates a new WebRTC manager
func NewManager(opts ...ManagerOption) *Manager {
	m := &Manager{
		logger:    logrus.New(),
		rtpPacker: video.NewRTPPacker(),
		nalParser: video.NewNALParser(),
		iceServers: []webrtc.ICEServer{
			{URLs: []string{"stun:stun.l.google.com:19302"}},
		},
	}
	for _, opt := range opts {
		opt(m)
	}
	return m
}

// CreateOffer creates a new WebRTC offer
func (m *Manager) CreateOffer() (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if err := m.initializePeerConnection(); err != nil {
		return "", err
	}

	offer, err := m.peerConnection.CreateOffer(nil)
	if err != nil {
		return "", fmt.Errorf("failed to create offer: %w", err)
	}

	if err := m.peerConnection.SetLocalDescription(offer); err != nil {
		return "", fmt.Errorf("failed to set local description: %w", err)
	}

	return offer.SDP, nil
}

// CreateAnswer creates an answer from a remote offer
func (m *Manager) CreateAnswer(remoteSDP string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if err := m.initializePeerConnection(); err != nil {
		return "", err
	}

	offer := webrtc.SessionDescription{
		Type: webrtc.SDPTypeOffer,
		SDP:  remoteSDP,
	}

	if err := m.peerConnection.SetRemoteDescription(offer); err != nil {
		return "", fmt.Errorf("failed to set remote description: %w", err)
	}

	answer, err := m.peerConnection.CreateAnswer(nil)
	if err != nil {
		return "", fmt.Errorf("failed to create answer: %w", err)
	}

	if err := m.peerConnection.SetLocalDescription(answer); err != nil {
		return "", fmt.Errorf("failed to set local description: %w", err)
	}

	return answer.SDP, nil
}

// SetAnswer sets the remote answer
func (m *Manager) SetAnswer(sdp string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.peerConnection == nil {
		return fmt.Errorf("peer connection not initialized")
	}

	answer := webrtc.SessionDescription{
		Type: webrtc.SDPTypeAnswer,
		SDP:  sdp,
	}

	return m.peerConnection.SetRemoteDescription(answer)
}

// AddICECandidate adds an ICE candidate
func (m *Manager) AddICECandidate(candidate, sdpMid string, sdpMLineIndex int) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.peerConnection == nil {
		return fmt.Errorf("peer connection not initialized")
	}

	return m.peerConnection.AddICECandidate(webrtc.ICECandidateInit{
		Candidate:     candidate,
		SDPMid:        &sdpMid,
		SDPMLineIndex: &sdpMLineIndex,
	})
}

// SendVideo sends video data to the video track
func (m *Manager) SendVideo(data []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.videoTrack == nil {
		return errors.New("video track not initialized")
	}

	// Parse NAL units from the H.264 stream
	nalUnits, err := m.nalParser.Parse(data)
	if err != nil {
		m.logger.Debugf("Failed to parse NAL units: %v", err)
		return nil
	}

	if len(nalUnits) == 0 {
		return nil
	}

	// Extract and cache SPS/PPS
	m.nalParser.ExtractSPSPPS(nalUnits)

	// Initialize frame count if needed
	if m.startTime.IsZero() {
		m.startTime = time.Now()
	}

	// Calculate timestamp (90000 Hz clock rate)
	elapsed := time.Since(m.startTime)
	timestamp := uint32(elapsed.Seconds() * float64(video.ClockRate))

	// Track frame stats
	m.frameCount++

	// Check if this is a keyframe
	isKeyFrame := m.nalParser.IsKeyFrame(nalUnits)

	// Pack and send each NAL unit
	for _, unit := range nalUnits {
		var packets []*rtp.Packet

		// For keyframes, prepend SPS/PPS if available
		if isKeyFrame && (unit.Type == video.NALTypeIDR) && m.nalParser.HasSPSPPS() {
			packets = m.rtpPacker.PackWithSPSPPS(
				unit.Data,
				m.nalParser.GetSPS(),
				m.nalParser.GetPPS(),
				timestamp,
			)
		} else {
			packets = m.rtpPacker.Pack(unit.Data, timestamp)
		}

		// Send each RTP packet
		for _, pkt := range packets {
			if err := m.sendRTPPacket(pkt); err != nil {
				m.logger.Warnf("Failed to send RTP packet: %v", err)
				return err
			}
		}
	}

	// Log stats every 100 frames
	if m.frameCount%100 == 0 {
		fps := float64(m.frameCount) / time.Since(m.startTime).Seconds()
		m.logger.Debugf("WebRTC stats: frames=%d, fps=%.2f, isKeyFrame=%v", m.frameCount, fps, isKeyFrame)
	}

	return nil
}

// sendRTPPacket sends an RTP packet via the track
func (m *Manager) sendRTPPacket(pkt *rtp.Packet) error {
	if m.videoTrack == nil {
		return fmt.Errorf("video track not initialized")
	}

	_, err := m.videoTrack.WriteRTP(pkt)
	return err
}

// GetStats returns current streaming statistics
func (m *Manager) GetStats() map[string]interface{} {
	m.mu.Lock()
	defer m.mu.Unlock()

	fps := 0.0
	if !m.startTime.IsZero() && m.frameCount > 0 {
		fps = float64(m.frameCount) / time.Since(m.startTime).Seconds()
	}

	return map[string]interface{}{
		"frameCount": m.frameCount,
		"fps":        fps,
		"startTime":  m.startTime,
		"hasSPS":     m.nalParser.GetSPS() != nil,
		"hasPPS":     m.nalParser.GetPPS() != nil,
	}
}

// ResetStats resets the streaming statistics
func (m *Manager) ResetStats() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.frameCount = 0
	m.startTime = time.Time{}
}

// Close closes the WebRTC connection
func (m *Manager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.peerConnection != nil {
		return m.peerConnection.Close()
	}
	return nil
}

// SetOnICECandidate sets the callback for ICE candidate events
func (m *Manager) SetOnICECandidate(callback func(*webrtc.ICECandidate)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.onICECandidate = callback
}

// GetConnectionState returns the current connection state
func (m *Manager) GetConnectionState() webrtc.PeerConnectionState {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.peerConnection == nil {
		return webrtc.PeerConnectionStateNew
	}
	return m.peerConnection.ConnectionState()
}

func (m *Manager) initializePeerConnection() error {
	if m.peerConnection != nil {
		return nil
	}

	// Initialize video processing components
	if m.rtpPacker == nil {
		m.rtpPacker = video.NewRTPPacker()
	}
	if m.nalParser == nil {
		m.nalParser = video.NewNALParser()
	}

	// Create MediaEngine
	mediaEngine := webrtc.NewMediaEngine()
	if err := mediaEngine.RegisterCodec(webrtc.RTPCodecParameters{
		RTPCodecCapability: webrtc.RTPCodecCapability{
			MimeType:     webrtc.MimeTypeH264,
			ClockRate:    video.ClockRate,
			Channels:     0,
			SDPFmtpLine:  "profile-level-id=42e01f;level-asymmetry-allowed=1;packetization-mode=1",
			RTCPFeedback: []webrtc.RTCPFeedback{
				{Type: webrtc.TypeRTCPFBNACK},
				{Type: webrtc.TypeRTCPFBNACKPLI},
				{Type: "fir"},
			},
		},
		PayloadType: video.DefaultPayloadType,
	}, webrtc.RTPCodecTypeVideo); err != nil {
		return err
	}

	// Create API with optional ICE port range
	var api *webrtc.API
	if m.icePorts.Min > 0 && m.icePorts.Max > 0 {
		settingEngine := webrtc.SettingEngine{}
		settingEngine.SetEphemeralUDPPortRange(m.icePorts.Min, m.icePorts.Max)
		api = webrtc.NewAPI(
			webrtc.WithMediaEngine(mediaEngine),
			webrtc.WithSettingEngine(settingEngine),
		)
	} else {
		api = webrtc.NewAPI(webrtc.WithMediaEngine(mediaEngine))
	}

	// Create peer connection with configured ICE servers
	config := webrtc.Configuration{
		ICEServers: m.iceServers,
	}

	pc, err := api.NewPeerConnection(config)
	if err != nil {
		return fmt.Errorf("failed to create peer connection: %w", err)
	}

	// Create video track
	videoTrack, err := webrtc.NewTrackLocalStaticSample(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeH264},
		"video",
		"screen",
	)
	if err != nil {
		return fmt.Errorf("failed to create video track: %w", err)
	}

	rtpSender, err := pc.AddTrack(videoTrack)
	if err != nil {
		return fmt.Errorf("failed to add video track: %w", err)
	}
	// rtpSender is kept for future use (e.g., for simulcast or RTCP)
	_ = rtpSender

	// Handle ICE candidates - forward to callback if set
	pc.OnICECandidate(func(candidate *webrtc.ICECandidate) {
		if candidate == nil {
			return
		}

		m.logger.Debugf("ICE candidate gathered: %v", candidate)

		// Call the registered callback if available
		if m.onICECandidate != nil {
			m.onICECandidate(candidate)
		}
	})

	// Handle connection state changes
	pc.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		m.logger.Infof("Connection state changed: %s", state)

		// Reset stats on connection
		if state == webrtc.PeerConnectionStateConnected {
			m.ResetStats()
		}
	})

	// Handle track events
	pc.OnTrack(func(track *webrtc.TrackRemote, receiver *webrtc.RTPReceiver) {
		m.logger.Debugf("Track received: %s", track.Codec().MimeType)
	})

	m.peerConnection = pc
	m.videoTrack = videoTrack

	return nil
}

// SignalingMessage represents a WebRTC signaling message
type SignalingMessage struct {
	Type      string          `json:"type"`
	SDP       string          `json:"sdp,omitempty"`
	Candidate json.RawMessage `json:"candidate,omitempty"`
}

// HandleSignaling handles WebRTC signaling over WebSocket (deprecated, use SignalingHandler)
func (m *Manager) HandleSignaling(conn *websocket.Conn) {
	handler := NewSignalingHandler(m, conn)
	handler.Handle()
}

// EncodeSDP encodes SDP to base64
func EncodeSDP(sdp string) string {
	return base64.StdEncoding.EncodeToString([]byte(sdp))
}

// DecodeSDP decodes SDP from base64
func DecodeSDP(encoded string) (string, error) {
	decoded, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return "", err
	}
	return string(decoded), nil
}
