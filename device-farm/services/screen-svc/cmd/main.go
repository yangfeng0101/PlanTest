package main

import (
	"github.com/gin-gonic/gin"
	"github.com/sirupsen/logrus"

	"screen-svc/internal/config"
	"screen-svc/internal/handler"
	"screen-svc/internal/session"
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

	logger.Info("Starting Screen Service v2.0 (LiveKit Mode)...")

	// Create session manager
	manager := session.NewManager()

	// Create handler
	h := handler.NewHandler(manager, cfg)

	// Create router
	router := gin.Default()

	// CORS middleware
	router.Use(func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		if origin != "" {
			c.Writer.Header().Set("Access-Control-Allow-Origin", origin)
			c.Writer.Header().Set("Vary", "Origin")
		}
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-CSRF-Token")
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
	logger.Infof("  POST /api/v1/sessions/:device_id/start")
	logger.Infof("  POST /api/v1/sessions/:device_id/stop")

	if err := router.Run(address); err != nil {
		logger.Fatalf("Failed to start server: %v", err)
	}
}
