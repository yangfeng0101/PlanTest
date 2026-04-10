package harmony

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"os/exec"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// Config holds HarmonyOS mirroring configuration
type Config struct {
	MaxFPS       int
	Quality      int // JPEG quality 1-100
	HDCPath      string // Path to hdc binary
	UseHOScrpy   bool   // Use HOScrpy for streaming if available
	HOScrpyPath  string // Path to HOScrpy binary
	ScreenWidth  int    // Default screen width if not detected
	ScreenHeight int    // Default screen height if not detected
}

// DefaultConfig returns default HarmonyOS mirroring configuration
func DefaultConfig() *Config {
	return &Config{
		MaxFPS:       30, // HarmonyOS can achieve similar FPS to Android
		Quality:      80,
		HDCPath:      "hdc",
		UseHOScrpy:   false, // Default to screenshot mode as HOScrpy may not be installed
		HOScrpyPath:  "hoscrpy",
		ScreenWidth:  1080,
		ScreenHeight: 2340, // Default to common HarmonyOS device resolution
	}
}

// HarmonyMirror manages HarmonyOS screen mirroring
type HarmonyMirror struct {
	serial       string
	config       *Config
	ctx          context.Context
	cancel       context.CancelFunc
	running      bool
	mu           sync.Mutex
	logger       *logrus.Logger
	frameChan    chan []byte
	screenWidth  int
	screenHeight int
	onError      func(error)
	hoscrpyCmd   *exec.Cmd
}

// HarmonyMirrorOption is a functional option for HarmonyMirror
type HarmonyMirrorOption func(*HarmonyMirror)

// WithLogger sets the logger
func WithLogger(logger *logrus.Logger) HarmonyMirrorOption {
	return func(m *HarmonyMirror) {
		m.logger = logger
	}
}

// WithOnError sets the error callback
func WithOnError(fn func(error)) HarmonyMirrorOption {
	return func(m *HarmonyMirror) {
		m.onError = fn
	}
}

// WithFrameChannel sets the frame output channel
func WithFrameChannel(ch chan []byte) HarmonyMirrorOption {
	return func(m *HarmonyMirror) {
		m.frameChan = ch
	}
}

// NewHarmonyMirror creates a new HarmonyOS mirror instance
func NewHarmonyMirror(serial string, config *Config, opts ...HarmonyMirrorOption) *HarmonyMirror {
	if config == nil {
		config = DefaultConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	m := &HarmonyMirror{
		serial:  serial,
		config:  config,
		ctx:     ctx,
		cancel:  cancel,
		logger:  logrus.New(),
		running: false,
	}

	for _, opt := range opts {
		opt(m)
	}

	return m
}

// Start starts the HarmonyOS screen mirroring
func (m *HarmonyMirror) Start() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.running {
		return nil
	}

	m.logger.Infof("Starting HarmonyOS mirroring for device %s", m.serial)

	// Try HOScrpy first if available
	if m.config.UseHOScrpy {
		if err := m.startHOScrpyStream(); err != nil {
			m.logger.Warnf("HOScrpy not available, falling back to screenshot mode: %v", err)
			go m.screenshotLoop()
		}
	} else {
		// Use screenshot-based mirroring
		go m.screenshotLoop()
	}

	m.running = true
	m.logger.Infof("HarmonyOS mirroring started for device %s", m.serial)

	return nil
}

// Stop stops the HarmonyOS screen mirroring
func (m *HarmonyMirror) Stop() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !m.running {
		return nil
	}

	m.running = false

	// Kill HOScrpy process if running
	if m.hoscrpyCmd != nil && m.hoscrpyCmd.Process != nil {
		m.hoscrpyCmd.Process.Kill()
		m.hoscrpyCmd = nil
	}

	if m.cancel != nil {
		m.cancel()
	}

	m.logger.Infof("HarmonyOS mirroring stopped for device %s", m.serial)
	return nil
}

// IsRunning returns whether mirroring is active
func (m *HarmonyMirror) IsRunning() bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.running
}

// GetScreenSize returns the device screen dimensions
func (m *HarmonyMirror) GetScreenSize() (width, height int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.screenWidth, m.screenHeight
}

// Read reads video data (implements io.Reader interface for compatibility)
func (m *HarmonyMirror) Read(buf []byte) (int, error) {
	if m.frameChan == nil {
		return 0, io.EOF
	}

	select {
	case frame := <-m.frameChan:
		if len(frame) > len(buf) {
			// Frame too large, truncate
			copy(buf, frame[:len(buf)])
			return len(buf), nil
		}
		copy(buf, frame)
		return len(frame), nil
	case <-m.ctx.Done():
		return 0, io.EOF
	}
}

// startHOScrpyStream starts HOScrpy for real-time streaming
func (m *HarmonyMirror) startHOScrpyStream() error {
	// Check if HOScrpy is available
	if _, err := exec.LookPath(m.config.HOScrpyPath); err != nil {
		return fmt.Errorf("HOScrpy not found: %w", err)
	}

	// Start HOScrpy process
	// HOScrpy command format similar to scrcpy:
	// hoscrpy -s <serial> --no-audio --video-codec=h264
	args := []string{
		"-s", m.serial,
		"--no-audio",
		"--video-codec=h264",
		"--video-source=display",
		fmt.Sprintf("--max-fps=%d", m.config.MaxFPS),
		"--stdout", // Output to stdout for piping
	}

	m.hoscrpyCmd = exec.CommandContext(m.ctx, m.config.HOScrpyPath, args...)

	stdout, err := m.hoscrpyCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	if err := m.hoscrpyCmd.Start(); err != nil {
		return fmt.Errorf("failed to start HOScrpy: %w", err)
	}

	// Start goroutine to read frames from stdout
	go m.readHOScrpyFrames(stdout)

	return nil
}

// readHOScrpyFrames reads H.264 frames from HOScrpy stdout
func (m *HarmonyMirror) readHOScrpyFrames(stdout io.Reader) {
	buf := make([]byte, 65536)

	for {
		select {
		case <-m.ctx.Done():
			return
		default:
			n, err := stdout.Read(buf)
			if err != nil {
				if err != io.EOF {
					m.logger.Warnf("HOScrpy read error: %v", err)
				}
				return
			}

			if n > 0 && m.frameChan != nil {
				frame := make([]byte, n)
				copy(frame, buf[:n])

				select {
				case m.frameChan <- frame:
				default:
					// Channel full, skip frame
				}
			}
		}
	}
}

// screenshotLoop captures screenshots via HDC snapshot_display command
func (m *HarmonyMirror) screenshotLoop() {
	frameInterval := time.Second / time.Duration(m.config.MaxFPS)
	ticker := time.NewTicker(frameInterval)
	defer ticker.Stop()

	for {
		select {
		case <-m.ctx.Done():
			return
		case <-ticker.C:
			frame, err := m.captureScreenshot()
			if err != nil {
				m.logger.Warnf("Failed to capture screenshot: %v", err)
				continue
			}

			if m.frameChan != nil {
				select {
				case m.frameChan <- frame:
				default:
					// Channel full, skip frame
				}
			}
		}
	}
}

// captureScreenshot captures a screenshot using HDC
func (m *HarmonyMirror) captureScreenshot() ([]byte, error) {
	// HarmonyOS uses snapshot_display for screenshots
	// hdc -t <serial> shell snapshot_display -f /data/local/tmp/screenshot.png
	// Then pull the file

	// Alternative: Use shell command to output directly
	// hdc -t <serial> shell "snapshot_display -f /dev/stdout 2>/dev/null" 2>/dev/null

	// For simplicity, we'll use a temp file approach
	tempPath := "/data/local/tmp/harmony_screenshot.png"

	// Take screenshot
	captureCmd := exec.CommandContext(
		m.ctx,
		m.config.HDCPath,
		"-t", m.serial,
		"shell",
		"snapshot_display",
		"-f", tempPath,
	)
	if err := captureCmd.Run(); err != nil {
		return nil, fmt.Errorf("snapshot_display failed: %w", err)
	}

	// Pull the file
	pullCmd := exec.CommandContext(
		m.ctx,
		m.config.HDCPath,
		"-t", m.serial,
		"file", "recv", tempPath, "-",
	)

	output, err := pullCmd.Output()
	if err != nil {
		return nil, fmt.Errorf("file recv failed: %w", err)
	}

	// Cleanup temp file
	cleanupCmd := exec.CommandContext(
		m.ctx,
		m.config.HDCPath,
		"-t", m.serial,
		"shell", "rm", "-f", tempPath,
	)
	cleanupCmd.Run() // Ignore cleanup errors

	// Update screen size on first frame
	if m.screenWidth == 0 || m.screenHeight == 0 {
		m.detectScreenSize(output)
	}

	return output, nil
}

// detectScreenSize detects screen dimensions from PNG header
func (m *HarmonyMirror) detectScreenSize(pngData []byte) {
	if len(pngData) < 24 {
		return
	}

	// PNG header: 8 bytes signature + 4 bytes length + 4 bytes type + width + height
	// IHDR chunk starts at byte 8
	// Width at bytes 16-19, Height at bytes 20-23 (big-endian)
	if string(pngData[12:16]) == "IHDR" {
		m.screenWidth = int(binary.BigEndian.Uint32(pngData[16:20]))
		m.screenHeight = int(binary.BigEndian.Uint32(pngData[20:24]))
		m.logger.Infof("Detected HarmonyOS screen size: %dx%d", m.screenWidth, m.screenHeight)
	}
}

// ScaleCoordinate scales a coordinate from video space to device screen space
func (m *HarmonyMirror) ScaleCoordinate(x, y int) (int, int) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// For HarmonyOS, coordinates are typically 1:1 with screen
	return x, y
}
