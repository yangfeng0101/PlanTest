package handler

import (
	"bytes"
	"context"
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
	deviceclient "screen-svc/internal/device"
	iosstream "screen-svc/internal/ios"
	"screen-svc/internal/session"
)

type Handler struct {
	manager          *session.Manager
	logger           *logrus.Logger
	cfg              *config.Config
	authClient       *screenauth.Client
	deviceClient     *deviceclient.Client
	iosMJPEGMu       sync.Mutex
	iosMJPEGByDevice map[string]string
	iosMJPEGTimers   map[string]*time.Timer
	deviceLeaseMu    sync.Mutex
	deviceLeaseByID  map[string]string
}

var iosMJPEGPrepareAttachTimeout = 30 * time.Second

func NewHandler(manager *session.Manager, cfg *config.Config) *Handler {
	return &Handler{
		manager:          manager,
		logger:           logrus.New(),
		cfg:              cfg,
		authClient:       screenauth.NewClient(cfg.Auth.TestServiceURL),
		deviceClient:     deviceclient.NewClient(cfg.Device.ServiceURL),
		iosMJPEGByDevice: make(map[string]string),
		iosMJPEGTimers:   make(map[string]*time.Timer),
		deviceLeaseByID:  make(map[string]string),
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
		api.GET("/sessions/:device_id/ios-mjpeg/ui-hierarchy", h.IOSMJPEGUIHierarchy)
		api.POST("/sessions/:device_id/ios-mjpeg/debug/:action", h.IOSMJPEGDebugAction)
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
	if h.canUseIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusOK, gin.H{
			"active":      true,
			"device_id":   deviceID,
			"mode":        "ios-mjpeg",
			"stage":       "streaming",
			"stage_label": "iOS MJPEG direct",
			"user_id":     user.ID,
		})
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
	if existing, exists := h.manager.GetByDevice(deviceID); exists {
		if h.cfg.Auth.Enabled && user.Role != "admin" && existing.UserID != user.ID {
			c.JSON(http.StatusForbidden, gin.H{"error": "device is already in use"})
			return
		}
		h.writeScreenSessionResponse(c, deviceID, user, existing, true)
		return
	}

	if err := h.acquireDeviceLease(c.Request.Context(), deviceID, user); err != nil {
		h.writeDeviceLeaseError(c, err)
		return
	}

	allowReplace := !h.cfg.Auth.Enabled || user.Role == "admin"
	s, reused, err := h.manager.StartSession(deviceID, user.ID, allowReplace, &h.cfg.LiveKit, &h.cfg.Scrcpy)
	if err != nil {
		h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
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
		h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to generate token"})
		return
	}
	if !reused {
		h.watchSessionDeviceLease(s)
	}

	payload := h.sessionResponse(s, true)
	h.addSessionStartFields(payload, s, deviceID, token, reused)
	c.JSON(http.StatusOK, payload)
}

func (h *Handler) writeScreenSessionResponse(c *gin.Context, deviceID string, user *screenauth.User, s *session.Session, reused bool) {
	token, err := h.generateToken(s.SessionID, user.ID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to generate token"})
		return
	}
	payload := h.sessionResponse(s, true)
	h.addSessionStartFields(payload, s, deviceID, token, reused)
	c.JSON(http.StatusOK, payload)
}

func (h *Handler) addSessionStartFields(payload gin.H, s *session.Session, deviceID, token string, reused bool) {
	videoWidth, videoHeight := s.VideoSize()

	payload["device_id"] = deviceID
	payload["livekit_url"] = h.cfg.LiveKit.PublicURL
	payload["token"] = token
	payload["video_width"] = videoWidth
	payload["video_height"] = videoHeight
	payload["reused"] = reused
	payload["message"] = "session started"
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
	h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
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
	if !h.canUseIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusConflict, gin.H{"error": "iOS MJPEG stream is not prepared or belongs to another user"})
		return
	}
	h.cancelIOSMJPEGCleanup(deviceID)

	ctx := c.Request.Context()
	stream, err := iosstream.StartAgentStreamSession(ctx, h.cfg.IOSAgent.URL, deviceID)
	if err != nil {
		h.logger.Warnf("failed to start iOS MJPEG stream for %s: %v", deviceID, err)
		h.releaseIOSMJPEG(deviceID, user)
		h.stopIOSMJPEGAgentBestEffort(ctx, deviceID)
		h.releaseTrackedDeviceLease(ctx, deviceID)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer func() {
		h.releaseIOSMJPEG(deviceID, user)
		h.stopIOSMJPEGAgentBestEffort(ctx, deviceID)
		h.releaseTrackedDeviceLease(ctx, deviceID)
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
	if _, exists := h.manager.GetByDevice(deviceID); exists {
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}
	if h.isIOSMJPEGActive(deviceID) {
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}
	if err := h.acquireDeviceLease(c.Request.Context(), deviceID, user); err != nil {
		h.writeDeviceLeaseError(c, err)
		return
	}
	if !h.acquireIOSMJPEG(deviceID, user) {
		h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
		c.JSON(http.StatusConflict, gin.H{"error": "device is already streaming"})
		return
	}

	stream, err := iosstream.StartAgentStreamSession(c.Request.Context(), h.cfg.IOSAgent.URL, deviceID)
	if err != nil {
		h.logger.Warnf("failed to prepare iOS MJPEG stream for %s: %v", deviceID, err)
		h.releaseIOSMJPEG(deviceID, user)
		h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	h.scheduleIOSMJPEGPrepareCleanup(deviceID, user)
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
	err := iosstream.StopAgentStreamSession(stopCtx, h.cfg.IOSAgent.URL, deviceID)
	h.releaseTrackedDeviceLease(c.Request.Context(), deviceID)
	if err != nil {
		h.logger.Warnf("failed to stop iOS MJPEG stream for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "iOS MJPEG stream stopped"})
}

func (h *Handler) IOSMJPEGDebugAction(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}
	if h.cfg.IOSAgent.URL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "IOS_AGENT_URL is not configured"})
		return
	}

	deviceID := c.Param("device_id")
	if !h.canUseIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusConflict, gin.H{"error": "iOS MJPEG stream is not active or belongs to another user"})
		return
	}

	action := c.Param("action")
	if !isIOSMJPEGDebugAction(action) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported iOS MJPEG debug action"})
		return
	}

	body, err := io.ReadAll(io.LimitReader(c.Request.Body, 64*1024))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if len(body) == 0 {
		body = []byte("{}")
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()
	endpoint := strings.TrimRight(h.cfg.IOSAgent.URL, "/") + "/devices/" + url.PathEscape(deviceID) + "/" + action
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		h.logger.Warnf("failed to proxy iOS MJPEG debug action %s for %s: %v", action, deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer resp.Body.Close()
	payload, _ := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}
	c.Data(resp.StatusCode, contentType, payload)
}

func (h *Handler) IOSMJPEGUIHierarchy(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}
	if h.cfg.IOSAgent.URL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "IOS_AGENT_URL is not configured"})
		return
	}

	deviceID := c.Param("device_id")
	if !h.canUseIOSMJPEG(deviceID, user) {
		c.JSON(http.StatusConflict, gin.H{"error": "iOS MJPEG stream is not active or belongs to another user"})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()
	source, err := iosstream.GetAgentSource(ctx, h.cfg.IOSAgent.URL, deviceID)
	if err != nil {
		h.logger.Warnf("failed to fetch iOS MJPEG UI hierarchy source for %s: %v", deviceID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}

	hierarchy, err := iosstream.ParseIOSHierarchy(source.Source, deviceID)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, hierarchy)
}

func isIOSMJPEGDebugAction(action string) bool {
	switch action {
	case "tap", "swipe", "long-press", "text", "clear-text":
		return true
	default:
		return false
	}
}

func (h *Handler) ensureIOSMJPEGDeviceReady(c *gin.Context, deviceID string) bool {
	reqCtx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	device, err := h.deviceClient.Get(reqCtx, deviceID)
	if err != nil {
		h.logger.Warnf("failed to validate iOS MJPEG device %s: %v", deviceID, err)
		h.writeDeviceLeaseError(c, err)
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

func (h *Handler) scheduleIOSMJPEGPrepareCleanup(deviceID string, user *screenauth.User) {
	h.iosMJPEGMu.Lock()
	if old := h.iosMJPEGTimers[deviceID]; old != nil {
		old.Stop()
	}
	h.iosMJPEGTimers[deviceID] = time.AfterFunc(iosMJPEGPrepareAttachTimeout, func() {
		h.iosMJPEGMu.Lock()
		owner, active := h.iosMJPEGByDevice[deviceID]
		if active && owner == user.ID {
			delete(h.iosMJPEGByDevice, deviceID)
			delete(h.iosMJPEGTimers, deviceID)
		}
		h.iosMJPEGMu.Unlock()
		if !active || owner != user.ID {
			return
		}

		h.logger.Warnf("iOS MJPEG prepare timed out before stream attach, releasing %s", deviceID)
		h.stopIOSMJPEGAgentBestEffort(context.Background(), deviceID)
		h.releaseTrackedDeviceLease(context.Background(), deviceID)
	})
	h.iosMJPEGMu.Unlock()
}

func (h *Handler) cancelIOSMJPEGCleanup(deviceID string) {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	if timer := h.iosMJPEGTimers[deviceID]; timer != nil {
		timer.Stop()
		delete(h.iosMJPEGTimers, deviceID)
	}
}

func (h *Handler) isIOSMJPEGActive(deviceID string) bool {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	_, exists := h.iosMJPEGByDevice[deviceID]
	return exists
}

func (h *Handler) canUseIOSMJPEG(deviceID string, user *screenauth.User) bool {
	h.iosMJPEGMu.Lock()
	defer h.iosMJPEGMu.Unlock()
	owner, exists := h.iosMJPEGByDevice[deviceID]
	if !exists {
		return false
	}
	return !h.cfg.Auth.Enabled || user.Role == "admin" || owner == user.ID
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
	if timer := h.iosMJPEGTimers[deviceID]; timer != nil {
		timer.Stop()
		delete(h.iosMJPEGTimers, deviceID)
	}
	if owner, exists := h.iosMJPEGByDevice[deviceID]; exists && (!h.cfg.Auth.Enabled || user.Role == "admin" || owner == user.ID) {
		delete(h.iosMJPEGByDevice, deviceID)
	}
}

func (h *Handler) acquireDeviceLease(ctx context.Context, deviceID string, user *screenauth.User) error {
	reqCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := h.deviceClient.Occupy(reqCtx, deviceID, user.ID); err != nil {
		return err
	}

	h.deviceLeaseMu.Lock()
	h.deviceLeaseByID[deviceID] = user.ID
	h.deviceLeaseMu.Unlock()
	return nil
}

func (h *Handler) releaseTrackedDeviceLease(ctx context.Context, deviceID string) bool {
	h.deviceLeaseMu.Lock()
	owner, exists := h.deviceLeaseByID[deviceID]
	if exists {
		delete(h.deviceLeaseByID, deviceID)
	}
	h.deviceLeaseMu.Unlock()
	if !exists {
		return false
	}

	verifyCtx, verifyCancel := context.WithTimeout(contextWithoutCancel(ctx), 5*time.Second)
	defer verifyCancel()
	if snapshot, err := h.deviceClient.Get(verifyCtx, deviceID); err == nil {
		if snapshot.OccupiedBy != "" && snapshot.OccupiedBy != owner {
			h.logger.Warnf("skip releasing device lease for %s: occupied by %s, screen owner was %s", deviceID, snapshot.OccupiedBy, owner)
			return false
		}
	} else {
		h.logger.Warnf("failed to verify device lease owner for %s before release: %v", deviceID, err)
	}

	releaseCtx, releaseCancel := context.WithTimeout(contextWithoutCancel(ctx), 10*time.Second)
	defer releaseCancel()
	if err := h.deviceClient.Release(releaseCtx, deviceID); err != nil {
		h.logger.Warnf("failed to release device lease for %s: %v", deviceID, err)
	}
	return true
}

func (h *Handler) watchSessionDeviceLease(s *session.Session) {
	go func() {
		<-s.Done()
		h.releaseTrackedDeviceLease(context.Background(), s.SerialNo)
	}()
}

func (h *Handler) stopIOSMJPEGAgentBestEffort(ctx context.Context, deviceID string) {
	stopCtx, cancel := context.WithTimeout(contextWithoutCancel(ctx), 10*time.Second)
	defer cancel()
	if err := iosstream.StopAgentStreamSession(stopCtx, h.cfg.IOSAgent.URL, deviceID); err != nil {
		h.logger.Warnf("failed to stop iOS MJPEG stream for %s: %v", deviceID, err)
	}
}

func (h *Handler) writeDeviceLeaseError(c *gin.Context, err error) {
	if errors.Is(err, deviceclient.ErrNotConfigured) {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	var statusErr *deviceclient.StatusError
	if errors.As(err, &statusErr) {
		switch statusErr.StatusCode {
		case http.StatusNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": statusErr.Error()})
		case http.StatusUnauthorized, http.StatusForbidden:
			c.JSON(statusErr.StatusCode, gin.H{"error": statusErr.Error()})
		case http.StatusBadRequest, http.StatusConflict:
			c.JSON(http.StatusConflict, gin.H{"error": statusErr.Error()})
		default:
			c.JSON(http.StatusBadGateway, gin.H{"error": statusErr.Error()})
		}
		return
	}
	c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
}

func contextWithoutCancel(ctx context.Context) context.Context {
	if ctx == nil {
		return context.Background()
	}
	return context.WithoutCancel(ctx)
}
