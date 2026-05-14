package session

import (
	"context"
	"log"
	"sync"
	"time"

	livekit "github.com/livekit/protocol/livekit"
	lksdk "github.com/livekit/server-sdk-go/v2"
	"screen-svc/internal/config"
	"screen-svc/internal/scrcpy"
	agentwebrtc "screen-svc/internal/webrtc"
)

type Session struct {
	SerialNo  string
	UserID    string
	SessionID string

	scrcpyServer   *scrcpy.Server
	controller     *scrcpy.Controller
	h264Track      *agentwebrtc.H264Track
	room           *lksdk.Room
	cancel         context.CancelFunc
	mu             sync.Mutex
	done           chan struct{}
	doneOnce       sync.Once
	viewers        map[string]struct{}
	viewerSeen     bool
	viewerIdleStop *time.Timer

	createdAt        time.Time
	scrcpyReadyAt    time.Time
	livekitReadyAt   time.Time
	trackPublishedAt time.Time
	firstFrameAt     time.Time
	firstKeyFrameAt  time.Time
	lastFrameAt      time.Time
	stage            string
	lastError        string
	frameCount       uint64
	keyFrameCount    uint64
}

func NewSession(serialNo, userID, sessionID string) *Session {
	return &Session{
		SerialNo:  serialNo,
		UserID:    userID,
		SessionID: sessionID,
		createdAt: time.Now(),
		stage:     "created",
		done:      make(chan struct{}),
		viewers:   make(map[string]struct{}),
	}
}

func (s *Session) Start(ctx context.Context, cfg *config.LiveKitConfig, scrcpyCfg *config.ScrcpyConfig) error {
	ctx, s.cancel = context.WithCancel(ctx)

	var err error
	s.setStage("starting_scrcpy")
	s.scrcpyServer, err = scrcpy.NewServer(s.SerialNo, scrcpy.ServerOptions{
		ServerPath:    scrcpyCfg.ServerPath,
		MaxResolution: scrcpyCfg.MaxResolution,
		MaxFPS:        scrcpyCfg.MaxFPS,
		BitRate:       scrcpyCfg.BitRate,
	})
	if err != nil {
		s.setError(err)
		return err
	}
	s.markScrcpyReady()

	s.controller = scrcpy.NewController(
		s.scrcpyServer.ControlSocket,
		int32(s.scrcpyServer.VideoWidth),
		int32(s.scrcpyServer.VideoHeight),
	)

	h264Track, track, err := agentwebrtc.NewH264Track()
	if err != nil {
		s.setError(err)
		return err
	}
	s.h264Track = h264Track

	controlChan := make(chan []byte, 100)

	roomCB := &lksdk.RoomCallback{
		OnParticipantConnected: func(participant *lksdk.RemoteParticipant) {
			s.markViewerConnected(participant.Identity())
		},
		OnParticipantDisconnected: func(participant *lksdk.RemoteParticipant) {
			s.markViewerDisconnected(participant.Identity())
		},
		ParticipantCallback: lksdk.ParticipantCallback{
			OnDataReceived: func(data []byte, params lksdk.DataReceiveParams) {
				select {
				case controlChan <- data:
				default:
					log.Printf("control channel full, dropping msg")
				}
			},
		},
	}

	s.setStage("connecting_livekit")
	s.room, err = lksdk.ConnectToRoom(
		cfg.URL,
		lksdk.ConnectInfo{
			APIKey:              cfg.APIKey,
			APISecret:           cfg.APISecret,
			RoomName:            s.SessionID,
			ParticipantIdentity: "agent-" + s.SerialNo,
		},
		roomCB,
	)
	if err != nil {
		s.setError(err)
		return err
	}
	s.markLiveKitReady()

	if _, err = s.room.LocalParticipant.PublishTrack(track, &lksdk.TrackPublicationOptions{
		Name:        "screen",
		Source:      livekit.TrackSource_SCREEN_SHARE,
		VideoWidth:  s.scrcpyServer.VideoWidth,
		VideoHeight: s.scrcpyServer.VideoHeight,
	}); err != nil {
		s.setError(err)
		return err
	}
	s.markTrackPublished()

	go s.streamingLoop(ctx)
	go s.controlLoop(ctx, controlChan)

	return nil
}

func (s *Session) controlLoop(ctx context.Context, ch <-chan []byte) {
	for {
		select {
		case <-ctx.Done():
			return
		case data := <-ch:
			if err := s.controller.HandleDataChannelMsg(data); err != nil {
				log.Printf("control error: %v", err)
			}
		}
	}
}

func (s *Session) streamingLoop(ctx context.Context) {
	defer s.Destroy()

	parser := scrcpy.NewH264Parser(s.scrcpyServer.VideoSocket)
	s.h264Track.SetParser(parser)
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		nalType, nalData, err := parser.ReadNALUnit()
		if err != nil {
			log.Printf("[%s] read NAL error: %v", s.SerialNo, err)
			s.setError(err)
			return
		}

		isKeyFrame := parser.IsKeyFrame(nalType)
		s.markFrame(isKeyFrame)

		if err := s.h264Track.FeedNALUnit(nalType, nalData, isKeyFrame); err != nil {
			log.Printf("[%s] feed NAL error: %v", s.SerialNo, err)
			s.setError(err)
		}
	}
}

func (s *Session) Destroy() {
	s.mu.Lock()
	if s.viewerIdleStop != nil {
		s.viewerIdleStop.Stop()
		s.viewerIdleStop = nil
	}
	cancel := s.cancel
	room := s.room
	scrcpyServer := s.scrcpyServer
	s.cancel = nil
	s.room = nil
	s.scrcpyServer = nil
	s.mu.Unlock()

	defer s.doneOnce.Do(func() {
		close(s.done)
	})

	if cancel != nil {
		cancel()
	}
	if room != nil {
		room.Disconnect()
	}
	if scrcpyServer != nil {
		scrcpyServer.Destroy()
	}
}

func (s *Session) markViewerConnected(identity string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if identity == "" || identity == "agent-"+s.SerialNo {
		return
	}
	if s.viewerIdleStop != nil {
		s.viewerIdleStop.Stop()
		s.viewerIdleStop = nil
	}
	s.viewers[identity] = struct{}{}
	s.viewerSeen = true
}

func (s *Session) markViewerDisconnected(identity string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if identity == "" || identity == "agent-"+s.SerialNo {
		return
	}
	delete(s.viewers, identity)
	if !s.viewerSeen || len(s.viewers) > 0 || s.viewerIdleStop != nil {
		return
	}

	s.viewerIdleStop = time.AfterFunc(10*time.Second, func() {
		s.mu.Lock()
		shouldDestroy := s.viewerSeen && len(s.viewers) == 0
		s.viewerIdleStop = nil
		s.mu.Unlock()
		if shouldDestroy {
			s.Destroy()
		}
	})
}

func (s *Session) Done() <-chan struct{} {
	return s.done
}

func (s *Session) VideoSize() (int, int) {
	if s.scrcpyServer == nil {
		return 0, 0
	}
	return s.scrcpyServer.VideoWidth, s.scrcpyServer.VideoHeight
}

type Diagnostics struct {
	Stage       string            `json:"stage"`
	StageLabel  string            `json:"stage_label"`
	CreatedAt   string            `json:"created_at,omitempty"`
	Timeline    map[string]string `json:"timeline"`
	DurationsMS map[string]int64  `json:"durations_ms"`

	FrameCount    uint64 `json:"frame_count"`
	KeyFrameCount uint64 `json:"key_frame_count"`
	LastError     string `json:"last_error,omitempty"`
}

func (s *Session) Diagnostics() Diagnostics {
	s.mu.Lock()
	defer s.mu.Unlock()

	timeline := make(map[string]string)
	addTime(timeline, "created_at", s.createdAt)
	addTime(timeline, "scrcpy_ready_at", s.scrcpyReadyAt)
	addTime(timeline, "livekit_ready_at", s.livekitReadyAt)
	addTime(timeline, "track_published_at", s.trackPublishedAt)
	addTime(timeline, "first_frame_at", s.firstFrameAt)
	addTime(timeline, "first_key_frame_at", s.firstKeyFrameAt)
	addTime(timeline, "last_frame_at", s.lastFrameAt)

	durations := make(map[string]int64)
	addDuration(durations, "scrcpy_ready", s.createdAt, s.scrcpyReadyAt)
	addDuration(durations, "livekit_ready", s.createdAt, s.livekitReadyAt)
	addDuration(durations, "track_published", s.createdAt, s.trackPublishedAt)
	addDuration(durations, "first_frame", s.createdAt, s.firstFrameAt)
	addDuration(durations, "first_key_frame", s.createdAt, s.firstKeyFrameAt)

	return Diagnostics{
		Stage:         s.stage,
		StageLabel:    stageLabel(s.stage),
		CreatedAt:     formatTime(s.createdAt),
		Timeline:      timeline,
		DurationsMS:   durations,
		FrameCount:    s.frameCount,
		KeyFrameCount: s.keyFrameCount,
		LastError:     s.lastError,
	}
}

func (s *Session) setStage(stage string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stage = stage
}

func (s *Session) setError(err error) {
	if err == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stage = "error"
	s.lastError = err.Error()
}

func (s *Session) markScrcpyReady() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.scrcpyReadyAt = time.Now()
	s.stage = "scrcpy_ready"
}

func (s *Session) markLiveKitReady() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.livekitReadyAt = time.Now()
	s.stage = "livekit_ready"
}

func (s *Session) markTrackPublished() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.trackPublishedAt = time.Now()
	s.stage = "track_published"
}

func (s *Session) markFrame(isKeyFrame bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	s.frameCount++
	s.lastFrameAt = now
	if s.firstFrameAt.IsZero() {
		s.firstFrameAt = now
		s.stage = "streaming"
	}
	if isKeyFrame {
		s.keyFrameCount++
		if s.firstKeyFrameAt.IsZero() {
			s.firstKeyFrameAt = now
		}
	}
}

func addTime(timeline map[string]string, key string, value time.Time) {
	if value.IsZero() {
		return
	}
	timeline[key] = formatTime(value)
}

func addDuration(durations map[string]int64, key string, start time.Time, end time.Time) {
	if start.IsZero() || end.IsZero() {
		return
	}
	durations[key] = end.Sub(start).Milliseconds()
}

func formatTime(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano)
}

func stageLabel(stage string) string {
	switch stage {
	case "created":
		return "已创建会话"
	case "starting_scrcpy":
		return "正在启动 scrcpy"
	case "scrcpy_ready":
		return "scrcpy 已就绪"
	case "connecting_livekit":
		return "正在连接视频通道"
	case "livekit_ready":
		return "视频通道已连接"
	case "track_published":
		return "视频轨道已发布，等待首帧"
	case "streaming":
		return "视频流正常"
	case "error":
		return "投屏链路异常"
	default:
		return "未知状态"
	}
}
