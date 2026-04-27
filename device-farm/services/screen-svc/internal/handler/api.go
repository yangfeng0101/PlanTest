package handler

import (
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
		c.JSON(http.StatusOK, gin.H{
			"active":     true,
			"session_id": s.SessionID,
			"device_id":  s.SerialNo,
			"user_id":    s.UserID,
			"room_name":  s.SessionID,
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
	s, err := h.manager.StartSession(deviceID, user.ID, &h.cfg.LiveKit, &h.cfg.Scrcpy)
	if err != nil {
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

	c.JSON(http.StatusOK, gin.H{
		"session_id":   s.SessionID,
		"device_id":    deviceID,
		"room_name":    s.SessionID,
		"livekit_url":  h.cfg.LiveKit.PublicURL,
		"token":        token,
		"video_width":  videoWidth,
		"video_height": videoHeight,
		"message":      "session started",
	})
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
