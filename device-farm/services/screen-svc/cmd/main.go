package main

import (
	"github.com/gin-gonic/gin"
	"github.com/pion/webrtc/v3"
	"github.com/sirupsen/logrus"

	"screen-svc/internal/config"
	"screen-svc/internal/handler"
	"screen-svc/internal/ios"
	"screen-svc/internal/scrcpy"
)

func main() {
	// Load configuration
	cfg := config.Load()

	// Setup logging
	logger := logrus.New()
	if cfg.LogLevel == "debug" {
		logger.SetLevel(logrus.DebugLevel)
		gin.SetMode(gin.DebugMode)
	} else {
		logger.SetLevel(logrus.InfoLevel)
		gin.SetMode(gin.ReleaseMode)
	}

	logger.Info("Starting Screen Service v2.0...")

	// Create scrcpy config
	scrcpyConfig := &scrcpy.Config{
		MaxResolution: cfg.Scrcpy.MaxResolution,
		MaxFPS:        cfg.Scrcpy.MaxFPS,
		BitRate:       cfg.Scrcpy.BitRate,
		Codec:         cfg.Scrcpy.Codec,
	}

	// Convert ICE servers from config to webrtc format
	iceServers := make([]webrtc.ICEServer, 0, len(cfg.WebRTC.ICEServers))
	for _, server := range cfg.WebRTC.ICEServers {
		iceServers = append(iceServers, webrtc.ICEServer{
			URLs: server.URLs,
		})
	}

	// Create screen manager with ICE servers
	// Use default iOS config for now
	iosConfig := ios.DefaultConfig()
	manager := handler.NewScreenManager(scrcpyConfig, iosConfig, iceServers)

	// Create handler
	h := handler.NewHandler(manager)

	// Create router
	router := gin.Default()

	// CORS middleware
	router.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	})

	// Setup routes using the handler
	h.SetupRoutes(router)

	// Start server
	address := cfg.GetAddress()
	logger.Infof("Server starting on %s", address)
	logger.Infof("API endpoints:")
	logger.Infof("  GET  /api/v1/health")
	logger.Infof("  GET  /api/v1/sessions")
	logger.Infof("  POST /api/v1/sessions/:device_id/start")
	logger.Infof("  POST /api/v1/sessions/:device_id/stop")
	logger.Infof("  POST /api/v1/sessions/:device_id/touch")
	logger.Infof("  POST /api/v1/sessions/:device_id/key")
	logger.Infof("  POST /api/v1/sessions/:device_id/text")
	logger.Infof("  POST /api/v1/sessions/:device_id/back")
	logger.Infof("  POST /api/v1/sessions/:device_id/home")
	logger.Infof("  POST /api/v1/sessions/:device_id/rotate")
	logger.Infof("WebSocket endpoints:")
	logger.Infof("  /ws/signaling/:device_id - WebRTC signaling")
	logger.Infof("  /ws/control/:device_id   - Control channel")

	if err := router.Run(address); err != nil {
		logger.Fatalf("Failed to start server: %v", err)
	}
}
