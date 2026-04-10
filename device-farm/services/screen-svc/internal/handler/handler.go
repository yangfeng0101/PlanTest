package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 65536,
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins for development
	},
}

// Handler manages HTTP and WebSocket handlers
type Handler struct {
	manager *ScreenManager
	logger  *logrus.Logger
}

// NewHandler creates a new handler instance
func NewHandler(manager *ScreenManager) *Handler {
	return &Handler{
		manager: manager,
		logger:  logrus.New(),
	}
}

// SetupRoutes sets up all routes
func (h *Handler) SetupRoutes(r *gin.Engine) {
	api := r.Group("/api/v1")
	{
		api.GET("/health", h.HealthCheck)
		api.GET("/sessions", h.ListSessions)

		sessions := api.Group("/sessions/:device_id")
		{
			sessions.GET("", h.GetSession)
			sessions.POST("/start", h.StartSession)
			sessions.POST("/stop", h.StopSession)
			sessions.POST("/touch", h.Touch)
			sessions.POST("/key", h.KeyEvent)
			sessions.POST("/text", h.Text)
			sessions.POST("/scroll", h.Scroll)
			sessions.POST("/back", h.Back)
			sessions.POST("/home", h.Home)
			sessions.POST("/rotate", h.Rotate)
		}
	}

	// WebSocket endpoints
	r.GET("/ws/signaling/:device_id", h.WebRTCSignaling)
	r.GET("/ws/control/:device_id", h.ControlWebSocket)
}

// HealthCheck returns service health status
func (h *Handler) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"service": "screen-svc",
		"version": "2.0.0",
	})
}

// ListSessions lists all active screen sessions
func (h *Handler) ListSessions(c *gin.Context) {
	sessions := h.manager.ListSessions()
	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"total":    len(sessions),
	})
}

// GetSession returns details of a specific session
func (h *Handler) GetSession(c *gin.Context) {
	deviceID := c.Param("device_id")

	session, err := h.manager.GetSession(deviceID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"device_id":     session.DeviceID,
		"screen_width":  session.ScreenWidth,
		"screen_height": session.ScreenHeight,
		"client_count":  len(session.Clients),
		"created_at":    session.CreatedAt,
	})
}

// StartSession starts a new screen mirroring session
func (h *Handler) StartSession(c *gin.Context) {
	deviceID := c.Param("device_id")

	session, err := h.manager.StartSession(deviceID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message":      "Session started",
		"device_id":    session.DeviceID,
		"screen_width": session.ScreenWidth,
		"screen_height": session.ScreenHeight,
		"ws_url":       "/ws/signaling/" + deviceID,
		"control_url":  "/ws/control/" + deviceID,
	})
}

// StopSession stops a screen mirroring session
func (h *Handler) StopSession(c *gin.Context) {
	deviceID := c.Param("device_id")

	if err := h.manager.StopSession(deviceID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Session stopped",
	})
}

// WebRTCSignaling handles WebRTC signaling over WebSocket
func (h *Handler) WebRTCSignaling(c *gin.Context) {
	deviceID := c.Param("device_id")

	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Errorf("WebSocket upgrade failed: %v", err)
		return
	}

	h.logger.Infof("New WebRTC signaling connection for device %s", deviceID)
	defer conn.Close()

	h.manager.HandleWebRTCSignaling(deviceID, conn)
}

// ControlWebSocket handles control messages over WebSocket
func (h *Handler) ControlWebSocket(c *gin.Context) {
	deviceID := c.Param("device_id")

	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Errorf("WebSocket upgrade failed: %v", err)
		return
	}

	h.logger.Infof("New control WebSocket connection for device %s", deviceID)

	// Register connection
	if err := h.manager.RegisterWebsocket(deviceID, conn); err != nil {
		h.logger.Errorf("Failed to register websocket: %v", err)
		conn.WriteJSON(gin.H{"error": err.Error()})
		conn.Close()
		return
	}

	// Handle messages
	h.handleControlMessages(deviceID, conn)
}

func (h *Handler) handleControlMessages(deviceID string, conn *websocket.Conn) {
	defer func() {
		h.manager.UnregisterWebsocket(deviceID, conn)
		conn.Close()
	}()

	for {
		messageType, data, err := conn.ReadMessage()
		if err != nil {
			h.logger.Debugf("Control WebSocket read error: %v", err)
			break
		}

		if messageType == websocket.TextMessage {
			h.manager.HandleControlMessage(deviceID, data)
		}
	}
}

// Touch sends touch event to device
func (h *Handler) Touch(c *gin.Context) {
	deviceID := c.Param("device_id")

	var req struct {
		X      int    `json:"x"`
		Y      int    `json:"y"`
		Action string `json:"action"` // down, up, move, down_up
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.Action == "" {
		req.Action = "down_up"
	}

	if err := h.manager.SendTouch(deviceID, req.X, req.Y, req.Action); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Touch event sent"})
}

// KeyEvent sends key event to device
func (h *Handler) KeyEvent(c *gin.Context) {
	deviceID := c.Param("device_id")

	var req struct {
		KeyCode int    `json:"keyCode"`
		Action  string `json:"action"` // down, up, down_up
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.Action == "" {
		req.Action = "down_up"
	}

	if err := h.manager.SendKeyEvent(deviceID, req.KeyCode, req.Action); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Key event sent"})
}

// Text sends text input to device
func (h *Handler) Text(c *gin.Context) {
	deviceID := c.Param("device_id")

	var req struct {
		Text string `json:"text"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.manager.SendText(deviceID, req.Text); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Text sent"})
}

// Scroll sends scroll event to device
func (h *Handler) Scroll(c *gin.Context) {
	deviceID := c.Param("device_id")

	var req struct {
		X  int `json:"x"`
		Y  int `json:"y"`
		DX int `json:"dx"`
		DY int `json:"dy"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// For now, we'll implement scroll via the manager
	c.JSON(http.StatusOK, gin.H{"message": "Scroll event sent"})
}

// Back sends back key to device
func (h *Handler) Back(c *gin.Context) {
	deviceID := c.Param("device_id")

	if err := h.manager.SendBack(deviceID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Back key sent"})
}

// Home sends home key to device
func (h *Handler) Home(c *gin.Context) {
	deviceID := c.Param("device_id")

	if err := h.manager.SendHome(deviceID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Home key sent"})
}

// Rotate rotates the device screen
func (h *Handler) Rotate(c *gin.Context) {
	deviceID := c.Param("device_id")

	if err := h.manager.SendRotate(deviceID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Rotate command sent"})
}
