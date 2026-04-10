package ios

import (
	"context"
	"encoding/binary"
	"fmt"
	"image"
	"image/jpeg"
	"io"
	"os/exec"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// Config holds iOS mirroring configuration
type Config struct {
	MaxFPS     int
	Quality    int // JPEG quality 1-100
	WDAHost    string
	WDAPort    int
	UseWDA     bool // Use WebDriverAgent for screenshots
	IdevicePath string // Path to idevicescreenshot binary
}

// DefaultConfig returns default iOS mirroring configuration
func DefaultConfig() *Config {
	return &Config{
		MaxFPS:     15, // iOS mirroring is typically slower than Android
		Quality:    80,
		WDAHost:    "localhost",
		WDAPort:    8100,
		UseWDA:     true,
		IdevicePath: "idevicescreenshot",
	}
}

// IOSMirror manages iOS screen mirroring
type IOSMirror struct {
	udid        string
	config      *Config
	ctx         context.Context
	cancel      context.CancelFunc
	running     bool
	mu          sync.Mutex
	logger      *logrus.Logger
	frameChan   chan []byte
	screenWidth int
	screenHeight int
	onError     func(error)
}

// IOSMirrorOption is a functional option for IOSMirror
type IOSMirrorOption func(*IOSMirror)

// WithLogger sets the logger
func WithLogger(logger *logrus.Logger) IOSMirrorOption {
	return func(m *IOSMirror) {
		m.logger = logger
	}
}

// WithOnError sets the error callback
func WithOnError(fn func(error)) IOSMirrorOption {
	return func(m *IOSMirror) {
		m.onError = fn
	}
}

// WithFrameChannel sets the frame output channel
func WithFrameChannel(ch chan []byte) IOSMirrorOption {
	return func(m *IOSMirror) {
		m.frameChan = ch
	}
}

// NewIOSMirror creates a new iOS mirror instance
func NewIOSMirror(udid string, config *Config, opts ...IOSMirrorOption) *IOSMirror {
	if config == nil {
		config = DefaultConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	m := &IOSMirror{
		udid:    udid,
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

// Start starts the iOS screen mirroring
func (m *IOSMirror) Start() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.running {
		return nil
	}

	m.logger.Infof("Starting iOS mirroring for device %s", m.udid)

	// Determine mirroring method
	if m.config.UseWDA {
		// Use WebDriverAgent for screenshots
		go m.wdaMirrorLoop()
	} else {
		// Use idevicescreenshot command
		go m.ideviceMirrorLoop()
	}

	m.running = true
	m.logger.Infof("iOS mirroring started for device %s", m.udid)

	return nil
}

// Stop stops the iOS screen mirroring
func (m *IOSMirror) Stop() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !m.running {
		return nil
	}

	m.running = false

	if m.cancel != nil {
		m.cancel()
	}

	m.logger.Infof("iOS mirroring stopped for device %s", m.udid)
	return nil
}

// IsRunning returns whether mirroring is active
func (m *IOSMirror) IsRunning() bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.running
}

// GetScreenSize returns the device screen dimensions
func (m *IOSMirror) GetScreenSize() (width, height int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.screenWidth, m.screenHeight
}

// Read reads video data (implements io.Reader interface for compatibility)
func (m *IOSMirror) Read(buf []byte) (int, error) {
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

// wdaMirrorLoop captures screenshots via WebDriverAgent HTTP API
func (m *IOSMirror) wdaMirrorLoop() {
	// Frame timing based on MaxFPS
	frameInterval := time.Second / time.Duration(m.config.MaxFPS)
	ticker := time.NewTicker(frameInterval)
	defer ticker.Stop()

	// Use curl to fetch screenshots from WDA
	// WDA endpoint: GET /session/:sessionId/screenshot
	wdaURL := fmt.Sprintf("http://%s:%d/session/0/screenshot", m.config.WDAHost, m.config.WDAPort)

	for {
		select {
		case <-m.ctx.Done():
			return
		case <-ticker.C:
			frame, err := m.captureWDAScreenshot(wdaURL)
			if err != nil {
				m.logger.Warnf("Failed to capture WDA screenshot: %v", err)
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

// captureWDAScreenshot captures a screenshot via WDA HTTP API
func (m *IOSMirror) captureWDAScreenshot(wdaURL string) ([]byte, error) {
	// Use curl to fetch screenshot from WDA
	// WDA returns base64 encoded PNG
	cmd := exec.CommandContext(m.ctx, "curl", "-s", "-X", "GET", wdaURL)
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("curl failed: %w", err)
	}

	// Parse JSON response to extract base64 image
	// Response format: {"value":"<base64>", "sessionId":"..."}
	frame, err := m.parseWDAScreenshotResponse(output)
	if err != nil {
		return nil, err
	}

	// Update screen size on first frame
	if m.screenWidth == 0 || m.screenHeight == 0 {
		m.detectScreenSize(frame)
	}

	return frame, nil
}

// parseWDAScreenshotResponse parses WDA screenshot JSON response
func (m *IOSMirror) parseWDAScreenshotResponse(data []byte) ([]byte, error) {
	// Simple JSON parsing for {"value":"<base64>"}
	// Find the base64 value between quotes
	valueStart := indexOf(data, []byte(`"value":"`))
	if valueStart == -1 {
		return nil, fmt.Errorf("invalid WDA response: missing value field")
	}
	valueStart += 9 // len('"value":"')

	valueEnd := indexOf(data[valueStart:], []byte(`"`))
	if valueEnd == -1 {
		return nil, fmt.Errorf("invalid WDA response: unterminated value")
	}

	base64Data := data[valueStart : valueStart+valueEnd]

	// Decode base64
	decoded := make([]byte, base64DecodedLen(len(base64Data)))
	n, err := base64Decode(decoded, base64Data)
	if err != nil {
		return nil, fmt.Errorf("base64 decode failed: %w", err)
	}

	return decoded[:n], nil
}

// ideviceMirrorLoop captures screenshots via idevicescreenshot command
func (m *IOSMirror) ideviceMirrorLoop() {
	frameInterval := time.Second / time.Duration(m.config.MaxFPS)
	ticker := time.NewTicker(frameInterval)
	defer ticker.Stop()

	for {
		select {
		case <-m.ctx.Done():
			return
		case <-ticker.C:
			frame, err := m.captureIdeviceScreenshot()
			if err != nil {
				m.logger.Warnf("Failed to capture idevice screenshot: %v", err)
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

// captureIdeviceScreenshot captures a screenshot using idevicescreenshot
func (m *IOSMirror) captureIdeviceScreenshot() ([]byte, error) {
	// idevicescreenshot outputs PNG to stdout
	cmd := exec.CommandContext(
		m.ctx,
		m.config.IdevicePath,
		"-u", m.udid,
		"--raw", // Output raw PNG to stdout
	)

	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("idevicescreenshot failed: %w", err)
	}

	// Update screen size on first frame
	if m.screenWidth == 0 || m.screenHeight == 0 {
		m.detectScreenSize(output)
	}

	return output, nil
}

// detectScreenSize detects screen dimensions from PNG header
func (m *IOSMirror) detectScreenSize(pngData []byte) {
	if len(pngData) < 24 {
		return
	}

	// PNG header: 8 bytes signature + 4 bytes length + 4 bytes type + width + height
	// IHDR chunk starts at byte 8
	// Width at bytes 16-19, Height at bytes 20-23 (big-endian)
	if string(pngData[12:16]) == "IHDR" {
		m.screenWidth = int(binary.BigEndian.Uint32(pngData[16:20]))
		m.screenHeight = int(binary.BigEndian.Uint32(pngData[20:24]))
		m.logger.Infof("Detected iOS screen size: %dx%d", m.screenWidth, m.screenHeight)
	}
}

// indexOf finds the first occurrence of subslice in slice
func indexOf(slice, subslice []byte) int {
	for i := 0; i <= len(slice)-len(subslice); i++ {
		match := true
		for j := 0; j < len(subslice); j++ {
			if slice[i+j] != subslice[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}

// base64DecodedLen calculates the decoded length of base64 data
func base64DecodedLen(encLen int) int {
	return (encLen*3 + 3) / 4
}

// base64Decode decodes base64 data (simple implementation)
func base64Decode(dst, src []byte) (int, error) {
	const base64Chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

	// Create decode table
	decodeTable := make([]byte, 256)
	for i := 0; i < 256; i++ {
		decodeTable[i] = 0xFF
	}
	for i := 0; i < 64; i++ {
		decodeTable[base64Chars[i]] = byte(i)
	}

	// Remove padding
	srcLen := len(src)
	for srcLen > 0 && src[srcLen-1] == '=' {
		srcLen--
	}

	dstIdx := 0
	for i := 0; i < srcLen; i += 4 {
		// Read up to 4 characters
		var n uint32
		count := 0
		for j := 0; j < 4 && i+j < srcLen; j++ {
			c := src[i+j]
			if c == '=' {
				break
			}
			v := decodeTable[c]
			if v == 0xFF {
				return 0, fmt.Errorf("invalid base64 character: %c", c)
			}
			n = (n << 6) | uint32(v)
			count++
		}

		// Output bytes based on count
		if count >= 2 {
			dst[dstIdx] = byte(n >> 10)
			dstIdx++
		}
		if count >= 3 {
			dst[dstIdx] = byte(n >> 2)
			dstIdx++
		}
		if count >= 4 {
			dst[dstIdx] = byte(n << 6)
			dstIdx++
		}
	}

	return dstIdx, nil
}

// ConvertPNGToH264 converts PNG frames to H.264 NAL units
// This is a placeholder - real implementation would use FFmpeg
func (m *IOSMirror) ConvertPNGToH264(pngData []byte) ([]byte, error) {
	// For now, just return the PNG data
	// Real implementation would:
	// 1. Decode PNG to raw pixels
	// 2. Encode to H.264 using FFmpeg or hardware encoder
	// 3. Return H.264 NAL units

	// This requires external FFmpeg integration
	// For MVP, we can use MJPEG instead of H.264 for iOS
	return pngData, nil
}

// ScaleCoordinate scales a coordinate from video space to device screen space
func (m *IOSMirror) ScaleCoordinate(x, y int) (int, int) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// For iOS, coordinates are typically 1:1 with screen
	return x, y
}

// SendTouch sends a touch event via WDA
func (m *IOSMirror) SendTouch(x, y int, action byte) error {
	if !m.config.UseWDA {
		return fmt.Errorf("touch requires WDA")
	}

	wdaURL := fmt.Sprintf("http://%s:%d/session/0/wda/tap/0", m.config.WDAHost, m.config.WDAPort)

	// Use curl to send touch
	cmd := exec.CommandContext(
		m.ctx,
		"curl", "-s", "-X", "POST",
		"-H", "Content-Type: application/json",
		"-d", fmt.Sprintf(`{"x":%d,"y":%d}`, x, y),
		wdaURL,
	)

	return cmd.Run()
}

// SendSwipe sends a swipe gesture via WDA
func (m *IOSMirror) SendSwipe(x1, y1, x2, y2 int) error {
	if !m.config.UseWDA {
		return fmt.Errorf("swipe requires WDA")
	}

	wdaURL := fmt.Sprintf("http://%s:%d/session/0/wda/performSwipe", m.config.WDAHost, m.config.WDAPort)

	cmd := exec.CommandContext(
		m.ctx,
		"curl", "-s", "-X", "POST",
		"-H", "Content-Type: application/json",
		"-d", fmt.Sprintf(`{"startX":%d,"startY":%d,"endX":%d,"endY":%d}`, x1, y1, x2, y2),
		wdaURL,
	)

	return cmd.Run()
}

// SendHome sends home button press via WDA
func (m *IOSMirror) SendHome() error {
	if !m.config.UseWDA {
		return fmt.Errorf("home button requires WDA")
	}

	wdaURL := fmt.Sprintf("http://%s:%d/session/0/wda/pressButton", m.config.WDAHost, m.config.WDAPort)

	cmd := exec.CommandContext(
		m.ctx,
		"curl", "-s", "-X", "POST",
		"-H", "Content-Type: application/json",
		"-d", `{"name":"home"}`,
		wdaURL,
	)

	return cmd.Run()
}

// ImageToJPEG converts image.Image to JPEG bytes
func ImageToJPEG(img image.Image, quality int) ([]byte, error) {
	buf := make([]byte, 0, 1024*1024) // 1MB initial capacity
	w := &byteWriter{buf: buf}
	err := jpeg.Encode(w, img, &jpeg.Options{Quality: quality})
	return w.buf, err
}

// byteWriter implements io.Writer for a byte slice
type byteWriter struct {
	buf []byte
}

func (w *byteWriter) Write(p []byte) (int, error) {
	w.buf = append(w.buf, p...)
	return len(p), nil
}
