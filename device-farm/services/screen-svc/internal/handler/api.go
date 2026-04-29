package handler

import (
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	lkauth "github.com/livekit/protocol/auth"
	"github.com/sirupsen/logrus"

	screenauth "screen-svc/internal/auth"
	"screen-svc/internal/config"
	"screen-svc/internal/session"
)

type Handler struct {
	manager    *session.Manager
	logger     *logrus.Logger
	cfg        *config.Config
	authClient *screenauth.Client
}

func NewHandler(manager *session.Manager, cfg *config.Config) *Handler {
	return &Handler{
		manager:    manager,
		logger:     logrus.New(),
		cfg:        cfg,
		authClient: screenauth.NewClient(cfg.Auth.TestServiceURL),
	}
}

func (h *Handler) SetupRoutes(r *gin.Engine) {
	api := r.Group("/api/v1")
	{
		api.GET("/health", h.HealthCheck)
		api.GET("/sessions/:device_id", h.GetSession)
		api.POST("/sessions/:device_id/start", h.StartSession)
		api.POST("/sessions/:device_id/stop", h.StopSession)
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
