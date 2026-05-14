package handler

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	lkauth "github.com/livekit/protocol/auth"
	"github.com/sirupsen/logrus"

	screenauth "screen-svc/internal/auth"
	"screen-svc/internal/config"
	iosstream "screen-svc/internal/ios"
	"screen-svc/internal/session"
)

type Handler struct {
	manager          *session.Manager
	logger           *logrus.Logger
	cfg              *config.Config
	authClient       *screenauth.Client
	iosMJPEGMu       sync.Mutex
	iosMJPEGByDevice map[string]string
}

type deviceSnapshot struct {
	ID           string `json:"id"`
	OS           string `json:"os"`
	Status       string `json:"status"`
	Capabilities struct {
		ScreenMirror bool `json:"screen_mirror"`
	} `json:"capabilities"`
}

func NewHandler(manager *session.Manager, cfg *config.Config) *Handler {
	return &Handler{
		manager:          manager,
		logger:           logrus.New(),
		cfg:              cfg,
		authClient:       screenauth.NewClient(cfg.Auth.TestServiceURL),
		iosMJPEGByDevice: make(map[string]string),
	}
}

func (h *Handler) SetupRoutes(r *gin.Engine) {
	api := r.Group("/api/v1")
	{
		api.GET("/health", h.HealthCheck)
		api.GET("/sessions/:device_id", h.GetSession)
		api.POST("/sessions/:device_id/start", h.StartSession)
		api.POST("/sessions/:device_id/stop", h.StopSession)
		api.POST("/sessions/:device_id/ios-mjpeg/prepare", h.PrepareIOSMJPEGStream)
		api.DELETE("/sessions/:device_id/ios-mjpeg", h.StopIOSMJPEGStream)
		api.GET("/sessions/:device_id/ios-mjpeg", h.IOSMJPEGStream)
	}
}

func (h *Handler) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"service": "screen-svc",
		"version": "2.0.0",
		"mode":    "livekit",
	})
}

func (h *Handler) generateToken(room, identity string) (string, error) {
	canSubscribe := true
	canPublish := false
	canPublishData := true
	at := lkauth.NewAccessToken(h.cfg.LiveKit.APIKey, h.cfg.LiveKit.APISecret)
	grant := &lkauth.VideoGrant{
		RoomJoin:       true,
		Room:           room,
		CanSubscribe:   &canSubscribe,
		CanPublish:     &canPublish,
		CanPublishData: &canPublishData,
	}
	at.SetVideoGrant(grant).
		SetIdentity(identity).
		SetValidFor(2 * time.Hour)

	return at.ToJWT()
}

func (h *Handler) currentUser(c *gin.Context) (*screenauth.User, bool) {
	if !h.cfg.Auth.Enabled {
		return &screenauth.User{ID: "anonymous", Username: "anonymous", Role: "admin"}, true
	}

	cookie, _ := c.Request.Cookie("access_token")
	user, err := h.authClient.Verify(c.Request.Context(), c.GetHeader("Authorization"), cookie)
	if err != nil {
		h.logger.Warnf("screen auth failed: %v", err)
		c.JSON(http.StatusUnauthorized, gin.H{"error": "authentication required"})
		return nil, false
	}
	return user, true
}

func (h *Handler) GetSession(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	deviceID := c.Param("device_id")
	if s, ok := h.manager.GetByDevice(deviceID); ok {
		if h.cfg.Auth.Enabled && user.Role != "admin" && s.UserID != user.ID {
			c.JSON(http.StatusOK, gin.H{
				"active":    true,
				"device_id": deviceID,
			})
			return
		}
		c.JSON(http.StatusOK, h.sessionResponse(s, true))
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"active":    false,
		"device_id": deviceID,
	})
}

func (h *Handler) StartSession(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	deviceID := c.Param("device_id")
	allowReplace := !h.cfg.Auth.Enabled || user.Role == "admin"
	s, reused, err := h.manager.StartSession(deviceID, user.ID, allowReplace, &h.cfg.LiveKit, &h.cfg.Scrcpy)
	if err != nil {
		if errors.Is(err, session.ErrDeviceInUse) {
			c.JSON(http.StatusForbidden, gin.H{"error": "device is already in use"})
			return
		}
		h.logger.Errorf("failed to start screen session for %s: %v", deviceID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to start screen session"})
		return
	}

	token, err := h.generateToken(s.SessionID, user.ID)
	if err != nil {
		h.manager.RemoveSession(s.SessionID)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to generate token"})
		return
	}
	videoWidth, videoHeight := s.VideoSize()

	payload := h.sessionResponse(s, true)
	payload["device_id"] = deviceID
	payload["livekit_url"] = h.cfg.LiveKit.PublicURL
	payload["token"] = token
	payload["video_width"] = videoWidth
	payload["video_height"] = videoHeight
	payload["reused"] = reused
	payload["message"] = "session started"

	c.JSON(http.StatusOK, payload)
}

func (h *Handler) sessionResponse(s *session.Session, includeUser bool) gin.H {
	diag := s.Diagnostics()
	payload := gin.H{
		"active":          true,
		"session_id":      s.SessionID,
		"device_id":       s.SerialNo,
		"room_name":       s.SessionID,
		"stage":           diag.Stage,
		"stage_label":     diag.StageLabel,
		"created_at":      diag.CreatedAt,
		"timeline":        diag.Timeline,
		"durations_ms":    diag.DurationsMS,
		"frame_count":     diag.FrameCount,
		"key_frame_count": diag.KeyFrameCount,
	}
	if diag.LastError != "" {
		payload["last_error"] = diag.LastError
	}
	if includeUser {
		payload["user_id"] = s.UserID
	}
	return payload
}

func (h *Handler) StopSession(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	deviceID := c.Param("device_id")
	s, exists := h.manager.GetByDevice(deviceID)
	if !exists {
		c.JSON(http.StatusOK, gin.H{"message": "session already stopped"})
		return
	}

	if h.cfg.Auth.Enabled && user.Role != "admin" && s.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "not allowed to stop this session"})
		return
	}

	h.manager.RemoveByDevice(deviceID)
	c.JSON(http.StatusOK, gin.H{
		"message":    "session stopped",
		"session_id": s.SessionID,
	})
}

func (h *Handler) IOSMJPEGStream(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}
	if h.cfg.IOSAgent.URL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "IOS_AGENT_URL is not configured"})
		return
	}

	deviceID := c.Param("device_id")
	if !h.ensureIOSMJPEGDeviceReady(c, deviceID) {
		return
	}
	if !h.acquireIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}
	defer h.releaseIOSMJPEG(deviceID, user)

	ctx := c.Request.Context()
	stream, err := iosstream.StartAgentStreamSession(ctx, h.cfg.IOSAgent.URL, deviceID)
	if err != nil {
		h.logger.Warnf("failed to start iOS MJPEG stream for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer func() {
		stopCtx, cancel := context.WithTimeout(contextWithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if err := iosstream.StopAgentStreamSession(stopCtx, h.cfg.IOSAgent.URL, deviceID); err != nil {
			h.logger.Warnf("failed to stop iOS MJPEG stream for %s: %v", deviceID, err)
		}
	}()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, stream.MJPEGURL, nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		h.logger.Warnf("failed to connect iOS MJPEG stream source for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		c.JSON(http.StatusBadGateway, gin.H{"error": string(body), "status": resp.StatusCode})
		return
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "multipart/x-mixed-replace; boundary=BoundaryString"
	}
	c.Header("Content-Type", contentType)
	c.Header("Cache-Control", "no-store")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)

	buf := make([]byte, 32*1024)
	_, _ = io.CopyBuffer(c.Writer, resp.Body, buf)
}

func (h *Handler) PrepareIOSMJPEGStream(c *gin.Context) {
	if _, ok := h.currentUser(c); !ok {
		return
	}
	if h.cfg.IOSAgent.URL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "IOS_AGENT_URL is not configured"})
		return
	}

	deviceID := c.Param("device_id")
	if !h.ensureIOSMJPEGDeviceReady(c, deviceID) {
		return
	}
	if _, exists := h.manager.GetByDevice(deviceID); exists {
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}
	if h.isIOSMJPEGActive(deviceID) {
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}

	stream, err := iosstream.StartAgentStreamSession(c.Request.Context(), h.cfg.IOSAgent.URL, deviceID)
	if err != nil {
		h.logger.Warnf("failed to prepare iOS MJPEG stream for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, stream)
}

func (h *Handler) StopIOSMJPEGStream(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}
	if h.cfg.IOSAgent.URL == "" {
		c.JSON(http.StatusOK, gin.H{"message": "iOS MJPEG stream already stopped"})
		return
	}

	deviceID := c.Param("device_id")
	if !h.canStopIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusForbidden, gin.H{"error": "not allowed to stop this iOS MJPEG stream"})
		return
	}
	h.releaseIOSMJPEG(deviceID, user)
	stopCtx, cancel := context.WithTimeout(contextWithoutCancel(c.Request.Context()), 10*time.Second)
	defer cancel()
	if err := iosstream.StopAgentStreamSession(stopCtx, h.cfg.IOSAgent.URL, deviceID); err != nil {
		h.logger.Warnf("failed to stop iOS MJPEG stream for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "iOS MJPEG stream stopped"})
}

func (h *Handler) ensureIOSMJPEGDeviceReady(c *gin.Context, deviceID string) bool {
	device, statusCode, err := h.fetchDeviceSnapshot(c.Request.Context(), deviceID)
	if err != nil {
		h.logger.Warnf("failed to validate iOS MJPEG device %s: %v", deviceID, err)
		c.JSON(statusCode, gin.H{"error": err.Error()})
		return false
	}

	if strings.ToLower(device.OS) != "ios" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "iOS MJPEG stream is only supported for iOS devices"})
		return false
	}
	if strings.ToLower(device.Status) != "online" {
		c.JSON(http.StatusConflict, gin.H{"error": "iOS device must be online and not busy before starting MJPEG stream"})
		return false
	}
	if !device.Capabilities.ScreenMirror {
		c.JSON(http.StatusBadRequest, gin.H{"error": "iOS screen mirror capability is not enabled for this device"})
		return false
	}
	return true
}

func (h *Handler) fetchDeviceSnapshot(ctx context.Context, deviceID string) (*deviceSnapshot, int, error) {
	baseURL := strings.TrimRight(h.cfg.Device.ServiceURL, "/")
	if baseURL == "" {
		return nil, http.StatusBadGateway, errors.New("device service URL is not configured")
	}

	reqCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	endpoint := baseURL + "/api/v1/devices/" + url.PathEscape(deviceID)
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, http.StatusBadGateway, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, http.StatusNotFound, errors.New("device not found")
	}
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		return nil, http.StatusBadGateway, errors.New(string(body))
	}

	var device deviceSnapshot
	if err := json.NewDecoder(resp.Body).Decode(&device); err != nil {
		return nil, http.StatusBadGateway, err
	}
	return &device, http.StatusOK, nil
}

func (h *Handler) acquireIOSMJPEG(deviceID string, user *screenauth.User) bool {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()

	if s, exists := h.manager.GetByDevice(deviceID); exists {
		if h.cfg.Auth.Enabled && user.Role != "admin" && s.UserID != user.ID {
			return false
		}
		return false
	}
	if _, exists := h.iosMJPEGByDevice[deviceID]; exists {
		return false
	}
	h.iosMJPEGByDevice[deviceID] = user.ID
	return true
}

func (h *Handler) isIOSMJPEGActive(deviceID string) bool {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	_, exists := h.iosMJPEGByDevice[deviceID]
	return exists
}

func (h *Handler) canStopIOSMJPEG(deviceID string, user *screenauth.User) bool {
	if !h.cfg.Auth.Enabled || user.Role == "admin" {
		return true
	}

	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	owner, exists := h.iosMJPEGByDevice[deviceID]
	return !exists || owner == user.ID
}

func (h *Handler) releaseIOSMJPEG(deviceID string, user *screenauth.User) {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	if owner, exists := h.iosMJPEGByDevice[deviceID]; exists && (!h.cfg.Auth.Enabled || user.Role == "admin" || owner == user.ID) {
		delete(h.iosMJPEGByDevice, deviceID)
	}
}

func contextWithoutCancel(ctx context.Context) context.Context {
	if ctx == nil {
		return context.Background()
	}
	return context.WithoutCancel(ctx)
}
