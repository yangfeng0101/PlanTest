package scrcpy

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

type ServerOptions struct {
	ServerPath    string
	MaxResolution int
	MaxFPS        int
	BitRate       int
}

type Server struct {
	SerialNo      string
	Options       ServerOptions
	VideoSocket   net.Conn
	ControlSocket net.Conn
	VideoPort     int
	ControlPort   int
	DeviceName    string
	VideoWidth    int
	VideoHeight   int
	cmd           *exec.Cmd
}

func NewServer(serialNo string, opts ServerOptions) (*Server, error) {
	if opts.ServerPath == "" {
		opts.ServerPath = "/usr/share/scrcpy/scrcpy-server"
	}
	if opts.MaxResolution <= 0 {
		opts.MaxResolution = 1080
	}
	if opts.MaxFPS <= 0 {
		opts.MaxFPS = 30
	}
	if opts.BitRate <= 0 {
		opts.BitRate = 2000000
	}

	s := &Server{
		SerialNo: serialNo,
		Options:  opts,
	}

	// 1. 推送 scrcpy-server.jar
	if err := s.pushServerJar(); err != nil {
		return nil, fmt.Errorf("push server jar: %w", err)
	}

	// 2. 建立端口转发。使用 tcp:0 让 adb server 在真实监听侧分配空闲端口。
	if err := s.setupForward(); err != nil {
		s.Destroy()
		return nil, fmt.Errorf("setup forward: %w", err)
	}

	// 3. 启动 scrcpy-server
	if err := s.startServer(); err != nil {
		s.Destroy()
		return nil, fmt.Errorf("start server: %w", err)
	}

	// 4. 连接视频 Socket（等待 server 就绪）
	if err := s.connectSockets(); err != nil {
		s.Destroy()
		return nil, fmt.Errorf("connect sockets: %w", err)
	}

	return s, nil
}

func (s *Server) pushServerJar() error {
	srcPath := s.Options.ServerPath
	destPath := "/data/local/tmp/scrcpy-server.jar"
	args := []string{"-s", s.SerialNo, "push", srcPath, destPath}
	if out, err := exec.Command("adb", args...).CombinedOutput(); err != nil {
		return fmt.Errorf("adb push failed: %s, %w", out, err)
	}
	return nil
}

func (s *Server) startServer() error {
	args := []string{
		"-s", s.SerialNo, "shell",
		"CLASSPATH=/data/local/tmp/scrcpy-server.jar",
		"app_process", "/",
		"com.genymobile.scrcpy.Server",
		"1.24",
		"log_level=info",
		"tunnel_forward=true",
		"bit_rate=" + strconv.Itoa(s.Options.BitRate),
		"max_size=" + strconv.Itoa(s.Options.MaxResolution),
		"max_fps=" + strconv.Itoa(s.Options.MaxFPS),
		"codec_options=i-frame-interval:int=1",
		"send_device_meta=true",
		"send_frame_meta=false",
		"lock_video_orientation=0",
	}
	s.cmd = exec.Command("adb", args...)
	s.cmd.Stdout = os.Stdout
	s.cmd.Stderr = os.Stderr
	return s.cmd.Start() // 异步启动
}

func (s *Server) setupForward() error {
	var err error
	s.VideoPort, err = s.setupScrcpyForward()
	if err != nil {
		return fmt.Errorf("video forward: %w", err)
	}

	s.ControlPort, err = s.setupScrcpyForward()
	if err != nil {
		return fmt.Errorf("control forward: %w", err)
	}

	return nil
}

func (s *Server) connectSockets() error {
	var err error
	host := adbForwardHost()
	videoAddr := net.JoinHostPort(host, strconv.Itoa(s.VideoPort))

	for i := 0; i < 100; i++ {
		s.VideoSocket, err = net.DialTimeout("tcp", videoAddr, 2*time.Second)
		if err == nil && s.readDummyByte() == nil {
			break
		}
		if s.VideoSocket != nil {
			s.VideoSocket.Close()
			s.VideoSocket = nil
		}
		time.Sleep(500 * time.Millisecond)
	}
	if err != nil {
		return fmt.Errorf("connect video socket: %w", err)
	}
	if s.VideoSocket == nil {
		return fmt.Errorf("connect video socket: server did not become ready")
	}

	controlAddr := net.JoinHostPort(host, strconv.Itoa(s.ControlPort))
	s.ControlSocket, err = net.DialTimeout("tcp", controlAddr, 2*time.Second)
	if err != nil {
		return fmt.Errorf("connect control socket: %w", err)
	}

	header := make([]byte, 68)
	if _, err = io.ReadFull(s.VideoSocket, header); err != nil {
		return fmt.Errorf("read device header: %w", err)
	}
	s.DeviceName = string(bytes.TrimRight(header[:64], "\x00"))
	s.VideoWidth = int(binary.BigEndian.Uint16(header[64:66]))
	s.VideoHeight = int(binary.BigEndian.Uint16(header[66:68]))
	if s.VideoWidth <= 0 || s.VideoHeight <= 0 {
		return fmt.Errorf("invalid video size %dx%d", s.VideoWidth, s.VideoHeight)
	}

	return nil
}

func (s *Server) readDummyByte() error {
	if err := s.VideoSocket.SetReadDeadline(time.Now().Add(500 * time.Millisecond)); err != nil {
		return err
	}
	defer s.VideoSocket.SetReadDeadline(time.Time{})

	buf := make([]byte, 1)
	_, err := s.VideoSocket.Read(buf)
	return err
}

func (s *Server) Destroy() {
	if s.VideoSocket != nil {
		s.VideoSocket.Close()
	}
	if s.ControlSocket != nil {
		s.ControlSocket.Close()
	}
	if s.cmd != nil && s.cmd.Process != nil {
		s.cmd.Process.Kill()
		s.cmd.Wait()
	}
	if s.VideoPort > 0 {
		exec.Command("adb", "-s", s.SerialNo, "forward", "--remove", fmt.Sprintf("tcp:%d", s.VideoPort)).Run()
	}
	if s.ControlPort > 0 {
		exec.Command("adb", "-s", s.SerialNo, "forward", "--remove", fmt.Sprintf("tcp:%d", s.ControlPort)).Run()
	}
}

func (s *Server) setupScrcpyForward() (int, error) {
	args := []string{"-s", s.SerialNo, "forward", "tcp:0", "localabstract:scrcpy"}
	out, err := exec.Command("adb", args...).CombinedOutput()
	if err == nil {
		port, parseErr := strconv.Atoi(strings.TrimSpace(string(out)))
		if parseErr == nil && port > 0 {
			return port, nil
		}
	}

	port, allocErr := freePort()
	if allocErr != nil {
		return 0, allocErr
	}
	fallbackArgs := []string{"-s", s.SerialNo, "forward", fmt.Sprintf("tcp:%d", port), "localabstract:scrcpy"}
	if fallbackOut, fallbackErr := exec.Command("adb", fallbackArgs...).CombinedOutput(); fallbackErr != nil {
		return 0, fmt.Errorf("adb forward failed: %s%s, %w", out, fallbackOut, fallbackErr)
	}
	return port, nil
}

func adbForwardHost() string {
	host := os.Getenv("ADB_SERVER_HOST")
	if host == "" {
		host = os.Getenv("ANDROID_ADB_SERVER_ADDRESS")
	}
	switch strings.ToLower(host) {
	case "", "localhost", "127.0.0.1", "::1":
		return "127.0.0.1"
	default:
		return host
	}
}

func freePort() (int, error) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer ln.Close()

	addr, ok := ln.Addr().(*net.TCPAddr)
	if !ok {
		return 0, fmt.Errorf("unexpected listener address %T", ln.Addr())
	}
	return addr.Port, nil
}
