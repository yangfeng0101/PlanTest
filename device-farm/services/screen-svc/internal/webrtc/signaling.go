package webrtc

import (
	"encoding/json"
	"fmt"
	"sync"

	"github.com/gorilla/websocket"
	"github.com/pion/webrtc/v3"
	"github.com/sirupsen/logrus"
)

// SignalingMessage represents a WebRTC signaling message
type SignalingMessage struct {
	Type      string          `json:"type"`
	SDP       string          `json:"sdp,omitempty"`
	Candidate json.RawMessage `json:"candidate,omitempty"`
}

// ICECandidateJSON represents an ICE candidate in JSON format
type ICECandidateJSON struct {
	Candidate     string `json:"candidate"`
	SDPMid        string `json:"sdpMid"`
	SDPMLineIndex int    `json:"sdpMLineIndex"`
}

// SignalingHandler handles WebRTC signaling over WebSocket
type SignalingHandler struct {
	manager *Manager
	conn    *websocket.Conn
	logger  *logrus.Logger
	mu      sync.Mutex
	closed  bool
}

// NewSignalingHandler creates a new signaling handler
func NewSignalingHandler(manager *Manager, conn *websocket.Conn) *SignalingHandler {
	return &SignalingHandler{
		manager: manager,
		conn:    conn,
		logger:  logrus.New(),
	}
}

// Handle handles the signaling session
func (h *SignalingHandler) Handle() error {
	// Set up ICE candidate callback to send candidates to client
	h.manager.SetOnICECandidate(func(candidate *webrtc.ICECandidate) {
		if candidate == nil {
			return
		}

		h.mu.Lock()
		defer h.mu.Unlock()

		if h.closed {
			return
		}

		// Convert to JSON format
		candidateJSON := candidate.ToJSON()

		// Handle nil SDPMid and SDPMLineIndex safely
		sdpMid := ""
		if candidateJSON.SDPMid != nil {
			sdpMid = *candidateJSON.SDPMid
		}
		sdpMLineIndex := 0
		if candidateJSON.SDPMLineIndex != nil {
			sdpMLineIndex = int(*candidateJSON.SDPMLineIndex)
		}

		msg := SignalingMessage{
			Type: "candidate",
			Candidate: mustMarshalJSON(ICECandidateJSON{
				Candidate:     candidateJSON.Candidate,
				SDPMid:        sdpMid,
				SDPMLineIndex: sdpMLineIndex,
			}),
		}

		if err := h.conn.WriteJSON(msg); err != nil {
			h.logger.Warnf("Failed to send ICE candidate: %v", err)
		} else {
			h.logger.Debugf("Sent ICE candidate: %s", candidateJSON.Candidate[:50])
		}
	})

	// Handle incoming messages
	for {
		_, message, err := h.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				h.logger.Debugf("WebSocket closed: %v", err)
			}
			return err
		}

		var msg SignalingMessage
		if err := json.Unmarshal(message, &msg); err != nil {
			h.logger.Warnf("Failed to parse signaling message: %v", err)
			continue
		}

		switch msg.Type {
		case "offer":
			if err := h.handleOffer(msg.SDP); err != nil {
				h.logger.Errorf("Failed to handle offer: %v", err)
				h.sendError(err.Error())
			}

		case "answer":
			if err := h.handleAnswer(msg.SDP); err != nil {
				h.logger.Errorf("Failed to handle answer: %v", err)
			}

		case "candidate":
			if err := h.handleCandidate(msg.Candidate); err != nil {
				h.logger.Errorf("Failed to handle candidate: %v", err)
			}

		default:
			h.logger.Warnf("Unknown signaling message type: %s", msg.Type)
		}
	}
}

// handleOffer handles an offer from the client
func (h *SignalingHandler) handleOffer(sdp string) error {
	h.logger.Debug("Received offer, creating answer...")

	answer, err := h.manager.CreateAnswer(sdp)
	if err != nil {
		return fmt.Errorf("failed to create answer: %w", err)
	}

	// Send answer back
	msg := SignalingMessage{
		Type: "answer",
		SDP:  answer,
	}

	h.mu.Lock()
	defer h.mu.Unlock()

	if err := h.conn.WriteJSON(msg); err != nil {
		return fmt.Errorf("failed to send answer: %w", err)
	}

	h.logger.Debug("Sent answer")
	return nil
}

// handleAnswer handles an answer from the client
func (h *SignalingHandler) handleAnswer(sdp string) error {
	h.logger.Debug("Received answer")
	return h.manager.SetAnswer(sdp)
}

// handleCandidate handles an ICE candidate from the client
func (h *SignalingHandler) handleCandidate(raw json.RawMessage) error {
	var candidate ICECandidateJSON
	if err := json.Unmarshal(raw, &candidate); err != nil {
		return fmt.Errorf("failed to parse candidate: %w", err)
	}

	h.logger.Debugf("Received ICE candidate: %s...", candidate.Candidate[:min(50, len(candidate.Candidate))])

	return h.manager.AddICECandidate(
		candidate.Candidate,
		candidate.SDPMid,
		candidate.SDPMLineIndex,
	)
}

// sendError sends an error message to the client
func (h *SignalingHandler) sendError(message string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	msg := SignalingMessage{
		Type: "error",
		SDP:  message,
	}
	h.conn.WriteJSON(msg)
}

// Close closes the signaling handler
func (h *SignalingHandler) Close() {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.closed = true
}

// mustMarshalJSON marshals to JSON or panics
func mustMarshalJSON(v interface{}) json.RawMessage {
	data, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return data
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
