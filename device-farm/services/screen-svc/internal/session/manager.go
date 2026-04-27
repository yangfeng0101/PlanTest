package session

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"

	"screen-svc/internal/config"
)

var ErrDeviceInUse = errors.New("device is already in use")

type Manager struct {
	sessions map[string]*Session
	byDevice map[string]string
	mu       sync.Mutex
}

func NewManager() *Manager {
	return &Manager{
		sessions: make(map[string]*Session),
		byDevice: make(map[string]string),
	}
}

func (m *Manager) StartSession(deviceID, userID string, allowReplace bool, livekitCfg *config.LiveKitConfig, scrcpyCfg *config.ScrcpyConfig) (*Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if oldID, ok := m.byDevice[deviceID]; ok {
		if old, exists := m.sessions[oldID]; exists && old.UserID != userID && !allowReplace {
			return nil, ErrDeviceInUse
		}
		m.removeLocked(oldID)
	}

	sessionID := "screen-" + randomID()
	s := NewSession(deviceID, userID, sessionID)
	if err := s.Start(context.Background(), livekitCfg, scrcpyCfg); err != nil {
		s.Destroy()
		return nil, err
	}

	m.sessions[sessionID] = s
	m.byDevice[deviceID] = sessionID
	go m.cleanupWhenDone(sessionID, s)
	return s, nil
}

func (m *Manager) GetSession(sessionID string) (*Session, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.sessions[sessionID]
	return s, ok
}

func (m *Manager) GetByDevice(deviceID string) (*Session, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	sessionID, ok := m.byDevice[deviceID]
	if !ok {
		return nil, false
	}
	s, ok := m.sessions[sessionID]
	return s, ok
}

func (m *Manager) RemoveSession(sessionID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.removeLocked(sessionID)
}

func (m *Manager) RemoveByDevice(deviceID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	sessionID, ok := m.byDevice[deviceID]
	if !ok {
		return false
	}
	return m.removeLocked(sessionID)
}

func (m *Manager) removeLocked(sessionID string) bool {
	s, ok := m.sessions[sessionID]
	if !ok {
		return false
	}
	s.Destroy()
	delete(m.sessions, sessionID)
	delete(m.byDevice, s.SerialNo)
	return true
}

func (m *Manager) cleanupWhenDone(sessionID string, s *Session) {
	<-s.Done()

	m.mu.Lock()
	defer m.mu.Unlock()
	if current, ok := m.sessions[sessionID]; ok && current == s {
		delete(m.sessions, sessionID)
		delete(m.byDevice, s.SerialNo)
	}
}

func randomID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("%x", b)
	}
	return hex.EncodeToString(b)
}
