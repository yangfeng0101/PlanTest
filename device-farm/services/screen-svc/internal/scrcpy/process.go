package scrcpy

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"

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

// Start starts the scrcpy process using an ffmpeg pipeline for raw H264
func (p *Process) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.running {
		return nil
	}

	// 1. Get screen dimensions
	if err := p.fetchScreenSize(); err != nil {
		p.logger.Warnf("Failed to get screen size: %v, using defaults", err)
		p.screenWidth = 1080
		p.screenHeight = 1920
	}

	// 2. Resolve tunnel host IP
	tunnelIP := "127.0.0.1"
	if b, err := os.ReadFile("/etc/hosts"); err == nil {
		lines := strings.Split(string(b), "\n")
		for _, line := range lines {
			if strings.Contains(line, "host.docker.internal") && !strings.Contains(line, ":") {
				fields := strings.Fields(line)
				if len(fields) > 0 {
					tunnelIP = fields[0]
					break
				}
			}
		}
	}

	// 3. Build the pipeline command
	// scrcpy 1.24 -> MKV stream -> ffmpeg -> raw H264 NAL units
	pipeline := fmt.Sprintf(
		"scrcpy -s %s --no-display --max-size %d --bit-rate %d --max-fps %d --tunnel-host %s --record - --record-format mkv | ffmpeg -i - -c:v copy -f h264 -",
		p.deviceID, p.config.MaxResolution, p.config.BitRate, p.config.MaxFPS, tunnelIP,
	)

	p.logger.Infof("Starting video pipeline: %s", pipeline)

	p.cmd = exec.CommandContext(p.ctx, "sh", "-c", pipeline)
	
	// Pass through ADB environment variables
	p.cmd.Env = os.Environ()
	p.cmd.Env = append(p.cmd.Env, "SDL_VIDEODRIVER=dummy")

	var err error
	p.stdout, err = p.cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	p.stderr, err = p.cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("failed to create stderr pipe: %w", err)
	}

	// 4. Start the process
	if err := p.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start pipeline: %w", err)
	}

	p.running = true
	go p.monitorStderr()
	go p.monitorProcess()

	p.logger.Infof("Video pipeline started for device %s", p.deviceID)
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

	if p.cmd != nil && p.cmd.Process != nil {
		p.cmd.Process.Kill()
		p.cmd.Wait()
	}

	p.logger.Infof("Video pipeline stopped for device %s", p.deviceID)
	return nil
}

// Read reads video data from the pipeline
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
	adbHost := os.Getenv("ANDROID_ADB_SERVER_ADDRESS")
	if adbHost == "" {
		adbHost = os.Getenv("ADB_SERVER_HOST")
	}
	adbPort := os.Getenv("ANDROID_ADB_SERVER_PORT")
	if adbPort == "" {
		adbPort = os.Getenv("ADB_SERVER_PORT")
	}

	var cmdArgs []string
	if adbHost != "" && adbHost != "localhost" {
		cmdArgs = append(cmdArgs, "-H", adbHost, "-P", adbPort)
	}
	cmdArgs = append(cmdArgs, "-s", p.deviceID, "shell", "wm", "size")

	cmd := exec.Command(p.config.ADBPath, cmdArgs...)
	output, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("failed to get screen size: %w", err)
	}

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

	if p.screenHeight > p.config.MaxResolution {
		p.videoHeight = p.config.MaxResolution
		p.videoWidth = p.screenWidth * p.config.MaxResolution / p.screenHeight
	} else {
		p.videoWidth = p.screenWidth
		p.videoHeight = p.screenHeight
	}

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
		if strings.Contains(line, "ERROR") || strings.Contains(line, "WARN") {
			p.logger.Warnf("[pipeline] %s", line)
		} else {
			p.logger.Debugf("[pipeline] %s", line)
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
		p.logger.Warnf("Pipeline process exited unexpectedly: %v", err)
		if p.onError != nil {
			p.onError(fmt.Errorf("pipeline process exited: %w", err))
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
