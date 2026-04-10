package scrcpy

import (
	"bufio"
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// Config holds scrcpy configuration
type Config struct {
	MaxResolution int
	MaxFPS        int
	BitRate       int
	Codec         string
	ScrcpyPath    string
	ADBPath       string
}

// DefaultConfig returns default scrcpy configuration
func DefaultConfig() *Config {
	return &Config{
		MaxResolution: 1080,
		MaxFPS:        30,
		BitRate:       2000000,
		Codec:         "h264",
		ScrcpyPath:    "scrcpy",
		ADBPath:       "adb",
	}
}

// Process manages a scrcpy server process
type Process struct {
	deviceID      string
	config        *Config
	cmd           *exec.Cmd
	stdin         io.WriteCloser
	stdout        io.Reader
	stderr        io.Reader
	running       bool
	mu            sync.Mutex
	logger        *logrus.Logger
	screenWidth   int
	screenHeight  int
	videoWidth    int
	videoHeight   int
	ctx           context.Context
	cancel        context.CancelFunc
	onError       func(error)
}

// ProcessOption is a functional option for Process
type ProcessOption func(*Process)

// WithLogger sets the logger
func WithLogger(logger *logrus.Logger) ProcessOption {
	return func(p *Process) {
		p.logger = logger
	}
}

// WithOnError sets the error callback
func WithOnError(fn func(error)) ProcessOption {
	return func(p *Process) {
		p.onError = fn
	}
}

// NewProcess creates a new scrcpy process
func NewProcess(deviceID string, config *Config, opts ...ProcessOption) *Process {
	if config == nil {
		config = DefaultConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	p := &Process{
		deviceID: deviceID,
		config:   config,
		ctx:      ctx,
		cancel:   cancel,
		logger:   logrus.New(),
	}

	for _, opt := range opts {
		opt(p)
	}

	return p
}

// Start starts the scrcpy process
func (p *Process) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.running {
		return nil
	}

	// Get screen dimensions first
	if err := p.fetchScreenSize(); err != nil {
		p.logger.Warnf("Failed to get screen size: %v, using defaults", err)
		p.screenWidth = 1080
		p.screenHeight = 1920
	}

	// Build scrcpy command with correct parameters for raw H.264 output
	// scrcpy 2.x command for raw stream output
	args := []string{
		"-s", p.deviceID,
		"--no-playback",      // Don't show window, just stream
		"--no-audio",         // No audio
		"--video-codec=h264", // H.264 codec
		"--video-source=display",
		fmt.Sprintf("--max-size=%d", p.config.MaxResolution),
		fmt.Sprintf("--video-bit-rate=%d", p.config.BitRate),
		fmt.Sprintf("--max-fps=%d", p.config.MaxFPS),
		"-",            // Output raw stream to stdout
	}

	p.logger.Infof("Starting scrcpy: %s %v", p.config.ScrcpyPath, args)

	p.cmd = exec.CommandContext(p.ctx, p.config.ScrcpyPath, args...)

	var err error
	p.stdin, err = p.cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	p.stdout, err = p.cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	p.stderr, err = p.cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("failed to create stderr pipe: %w", err)
	}

	// Start the process
	if err := p.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start scrcpy: %w", err)
	}

	p.running = true

	// Monitor stderr for diagnostics
	go p.monitorStderr()

	// Monitor process exit
	go p.monitorProcess()

	p.logger.Infof("Scrcpy process started for device %s", p.deviceID)

	return nil
}

// Stop stops the scrcpy process
func (p *Process) Stop() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if !p.running {
		return nil
	}

	p.running = false

	if p.cancel != nil {
		p.cancel()
	}

	if p.stdin != nil {
		p.stdin.Close()
	}

	if p.cmd != nil && p.cmd.Process != nil {
		// Give process time to exit gracefully
		done := make(chan error, 1)
		go func() {
			done <- p.cmd.Wait()
		}()

		select {
		case <-done:
			p.logger.Infof("Scrcpy process exited gracefully")
		case <-time.After(2 * time.Second):
			p.logger.Warnf("Scrcpy process didn't exit, killing")
			p.cmd.Process.Kill()
			p.cmd.Wait()
		}
	}

	p.logger.Infof("Scrcpy process stopped for device %s", p.deviceID)
	return nil
}

// Read reads video data from scrcpy output
func (p *Process) Read(buf []byte) (int, error) {
	if p.stdout == nil {
		return 0, io.EOF
	}
	return p.stdout.Read(buf)
}

// IsRunning returns whether the process is running
func (p *Process) IsRunning() bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.running
}

// GetScreenSize returns the device screen dimensions
func (p *Process) GetScreenSize() (width, height int) {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.screenWidth, p.screenHeight
}

// GetVideoSize returns the video stream dimensions
func (p *Process) GetVideoSize() (width, height int) {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.videoWidth, p.videoHeight
}

// fetchScreenSize gets the device screen dimensions via adb
func (p *Process) fetchScreenSize() error {
	cmd := exec.Command(p.config.ADBPath, "-s", p.deviceID, "shell", "wm", "size")
	output, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("failed to get screen size: %w", err)
	}

	// Parse output like "Physical size: 1080x1920"
	line := strings.TrimSpace(string(output))
	parts := strings.Split(line, ":")
	if len(parts) != 2 {
		return fmt.Errorf("unexpected wm size output: %s", line)
	}

	dims := strings.TrimSpace(parts[1])
	sizeParts := strings.Split(dims, "x")
	if len(sizeParts) != 2 {
		return fmt.Errorf("invalid size format: %s", dims)
	}

	p.screenWidth, _ = strconv.Atoi(sizeParts[0])
	p.screenHeight, _ = strconv.Atoi(sizeParts[1])

	// Calculate video dimensions based on max resolution
	if p.screenWidth > p.screenHeight {
		// Landscape
		if p.screenWidth > p.config.MaxResolution {
			p.videoWidth = p.config.MaxResolution
			p.videoHeight = p.screenHeight * p.config.MaxResolution / p.screenWidth
		} else {
			p.videoWidth = p.screenWidth
			p.videoHeight = p.screenHeight
		}
	} else {
		// Portrait
		if p.screenHeight > p.config.MaxResolution {
			p.videoHeight = p.config.MaxResolution
			p.videoWidth = p.screenWidth * p.config.MaxResolution / p.screenHeight
		} else {
			p.videoWidth = p.screenWidth
			p.videoHeight = p.screenHeight
		}
	}

	p.logger.Infof("Screen: %dx%d, Video: %dx%d", p.screenWidth, p.screenHeight, p.videoWidth, p.videoHeight)
	return nil
}

// monitorStderr reads stderr for diagnostics
func (p *Process) monitorStderr() {
	if p.stderr == nil {
		return
	}

	scanner := bufio.NewScanner(p.stderr)
	for scanner.Scan() {
		line := scanner.Text()
		// Log important messages
		if strings.Contains(line, "ERROR") || strings.Contains(line, "WARN") {
			p.logger.Warnf("[scrcpy stderr] %s", line)
		} else {
			p.logger.Debugf("[scrcpy stderr] %s", line)
		}
	}
}

// monitorProcess monitors the process state
func (p *Process) monitorProcess() {
	if p.cmd == nil {
		return
	}

	err := p.cmd.Wait()

	p.mu.Lock()
	wasRunning := p.running
	p.running = false
	p.mu.Unlock()

	if wasRunning {
		p.logger.Warnf("Scrcpy process exited unexpectedly: %v", err)
		if p.onError != nil {
			p.onError(fmt.Errorf("scrcpy process exited: %w", err))
		}
	}
}

// ScaleCoordinate scales a coordinate from video space to device screen space
func (p *Process) ScaleCoordinate(x, y int) (int, int) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.videoWidth == 0 || p.videoHeight == 0 {
		return x, y
	}

	scaledX := x * p.screenWidth / p.videoWidth
	scaledY := y * p.screenHeight / p.videoHeight

	return scaledX, scaledY
}

// parseUint16 reads a 2-byte big-endian uint16
func parseUint16(data []byte, offset int) uint16 {
	return binary.BigEndian.Uint16(data[offset : offset+2])
}

// parseUint32 reads a 4-byte big-endian uint32
func parseUint32(data []byte, offset int) uint32 {
	return binary.BigEndian.Uint32(data[offset : offset+4])
}

// parseUint64 reads an 8-byte big-endian uint64
func parseUint64(data []byte, offset int) uint64 {
	return binary.BigEndian.Uint64(data[offset : offset+8])
}
