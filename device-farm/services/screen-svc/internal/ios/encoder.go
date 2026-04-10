package ios

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os/exec"
	"sync"

	"github.com/sirupsen/logrus"
)

// VideoEncoder encodes PNG/MJPEG frames to H.264 for WebRTC streaming
type VideoEncoder struct {
	ctx      context.Context
	cancel   context.CancelFunc
	ffmpeg   *exec.Cmd
	stdin    io.WriteCloser
	stdout   io.Reader
	running  bool
	mu       sync.Mutex
	logger   *logrus.Logger
	config   *EncoderConfig
}

// EncoderConfig holds video encoder configuration
type EncoderConfig struct {
	Width       int
	Height      int
	FPS         int
	BitRate     int // in bps
	Preset      string
	Profile     string
	InputFormat string // png, mjpeg, etc
}

// DefaultEncoderConfig returns default encoder configuration
func DefaultEncoderConfig() *EncoderConfig {
	return &EncoderConfig{
		Width:       1080,
		Height:      1920,
		FPS:         15,
		BitRate:     2000000,
		Preset:      "ultrafast",
		Profile:     "baseline",
		InputFormat: "png",
	}
}

// NewVideoEncoder creates a new video encoder
func NewVideoEncoder(config *EncoderConfig) *VideoEncoder {
	if config == nil {
		config = DefaultEncoderConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &VideoEncoder{
		ctx:    ctx,
		cancel: cancel,
		config: config,
		logger: logrus.New(),
	}
}

// Start starts the FFmpeg encoder process
func (e *VideoEncoder) Start() error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.running {
		return nil
	}

	// Build FFmpeg command for PNG/MJPEG to H.264 encoding
	args := []string{
		"-f", "image2pipe", // Input format: image pipe
		"-vcodec", e.config.InputFormat, // Input codec (png, mjpeg)
		"-framerate", fmt.Sprintf("%d", e.config.FPS),
		"-i", "-", // Read from stdin
		"-vcodec", "libx264", // Output codec: H.264
		"-preset", e.config.Preset,
		"-profile:v", e.config.Profile,
		"-tune", "zerolatency", // Low latency for streaming
		"-g", fmt.Sprintf("%d", e.config.FPS*2), // Keyframe interval
		"-bf", "0", // No B-frames for lower latency
		"-b:v", fmt.Sprintf("%d", e.config.BitRate),
		"-pix_fmt", "yuv420p",
		"-f", "h264", // Output format: raw H.264
		"-",
	}

	e.ffmpeg = exec.CommandContext(e.ctx, "ffmpeg", args...)

	var err error
	e.stdin, err = e.ffmpeg.StdinPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	e.stdout, err = e.ffmpeg.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	if err := e.ffmpeg.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w", err)
	}

	e.running = true
	e.logger.Infof("Video encoder started (FFmpeg H.264)")

	return nil
}

// Stop stops the FFmpeg encoder process
func (e *VideoEncoder) Stop() error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if !e.running {
		return nil
	}

	e.running = false

	if e.stdin != nil {
		e.stdin.Close()
	}

	if e.cancel != nil {
		e.cancel()
	}

	if e.ffmpeg != nil && e.ffmpeg.Process != nil {
		e.ffmpeg.Process.Kill()
		e.ffmpeg.Wait()
	}

	e.logger.Infof("Video encoder stopped")
	return nil
}

// Encode encodes a single frame to H.264
func (e *VideoEncoder) Encode(frame []byte) ([]byte, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if !e.running || e.stdin == nil {
		return nil, fmt.Errorf("encoder not running")
	}

	// Write frame to FFmpeg stdin
	_, err := e.stdin.Write(frame)
	if err != nil {
		return nil, fmt.Errorf("failed to write frame: %w", err)
	}

	// Read encoded H.264 data
	// This is a simplified approach - real implementation would use
	// asynchronous reading with proper buffering
	buf := make([]byte, 65536)
	n, err := e.stdout.Read(buf)
	if err != nil && err != io.EOF {
		return nil, fmt.Errorf("failed to read encoded data: %w", err)
	}

	return buf[:n], nil
}

// IsRunning returns whether the encoder is running
func (e *VideoEncoder) IsRunning() bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.running
}

// MJPEGToH264Stream converts an MJPEG stream to H.264 NAL units
// This uses a pipe-based approach for real-time streaming
type MJPEGToH264Stream struct {
	ctx       context.Context
	cancel    context.CancelFunc
	cmd       *exec.Cmd
	stdin     io.WriteCloser
	stdout    io.Reader
	running   bool
	mu        sync.Mutex
	logger    *logrus.Logger
	frameChan chan []byte
	nalChan   chan []byte
}

// NewMJPEGToH264Stream creates a new MJPEG to H.264 stream converter
func NewMJPEGToH264Stream(width, height, fps, bitrate int) *MJPEGToH264Stream {
	ctx, cancel := context.WithCancel(context.Background())

	return &MJPEGToH264Stream{
		ctx:       ctx,
		cancel:    cancel,
		logger:    logrus.New(),
		frameChan: make(chan []byte, 10),
		nalChan:   make(chan []byte, 100),
	}
}

// Start starts the stream converter
func (s *MJPEGToH264Stream) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return nil
	}

	// FFmpeg command for MJPEG to H.264 streaming
	args := []string{
		"-f", "mjpeg",
		"-framerate", "15",
		"-i", "-",
		"-vcodec", "libx264",
		"-preset", "ultrafast",
		"-tune", "zerolatency",
		"-g", "30",
		"-bf", "0",
		"-b:v", "2000000",
		"-pix_fmt", "yuv420p",
		"-f", "h264",
		"-",
	}

	s.cmd = exec.CommandContext(s.ctx, "ffmpeg", args...)

	var err error
	s.stdin, err = s.cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	s.stdout, err = s.cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	if err := s.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w", err)
	}

	s.running = true

	// Start output reader goroutine
	go s.readOutput()

	s.logger.Infof("MJPEG to H.264 stream converter started")
	return nil
}

// Stop stops the stream converter
func (s *MJPEGToH264Stream) Stop() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return nil
	}

	s.running = false

	if s.stdin != nil {
		s.stdin.Close()
	}

	if s.cancel != nil {
		s.cancel()
	}

	if s.cmd != nil && s.cmd.Process != nil {
		s.cmd.Process.Kill()
		s.cmd.Wait()
	}

	close(s.frameChan)
	close(s.nalChan)

	return nil
}

// WriteFrame writes an MJPEG frame to the converter
func (s *MJPEGToH264Stream) WriteFrame(frame []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running || s.stdin == nil {
		return fmt.Errorf("converter not running")
	}

	_, err := s.stdin.Write(frame)
	return err
}

// ReadNAL reads an H.264 NAL unit from the converter
func (s *MJPEGToH264Stream) ReadNAL() ([]byte, error) {
	select {
	case nal := <-s.nalChan:
		return nal, nil
	case <-s.ctx.Done():
		return nil, io.EOF
	}
}

// readOutput continuously reads H.264 output from FFmpeg
func (s *MJPEGToH264Stream) readOutput() {
	buf := make([]byte, 65536)
	nalBuffer := bytes.NewBuffer(nil)

	for {
		select {
		case <-s.ctx.Done():
			return
		default:
			n, err := s.stdout.Read(buf)
			if err != nil {
				if err != io.EOF {
					s.logger.Warnf("Error reading FFmpeg output: %v", err)
				}
				return
			}

			// Append to NAL buffer
			nalBuffer.Write(buf[:n])

			// Try to extract complete NAL units
			// H.264 NAL units start with 0x00 0x00 0x00 0x01 or 0x00 0x00 0x01
			data := nalBuffer.Bytes()

			// Send raw H.264 data to NAL channel
			if len(data) > 0 {
				select {
				case s.nalChan <- append([]byte{}, data...):
					nalBuffer.Reset()
				default:
					// Channel full, drop
				}
			}
		}
	}
}

// IsRunning returns whether the converter is running
func (s *MJPEGToH264Stream) IsRunning() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.running
}
