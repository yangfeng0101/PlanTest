package session

import (
	"context"
	"log"
	"sync"

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

	scrcpyServer *scrcpy.Server
	controller   *scrcpy.Controller
	h264Track    *agentwebrtc.H264Track
	room         *lksdk.Room
	cancel       context.CancelFunc
	mu           sync.Mutex
	done         chan struct{}
	doneOnce     sync.Once
}

func NewSession(serialNo, userID, sessionID string) *Session {
	return &Session{
		SerialNo:  serialNo,
		UserID:    userID,
		SessionID: sessionID,
		done:      make(chan struct{}),
	}
}

func (s *Session) Start(ctx context.Context, cfg *config.LiveKitConfig, scrcpyCfg *config.ScrcpyConfig) error {
	ctx, s.cancel = context.WithCancel(ctx)

	var err error
	s.scrcpyServer, err = scrcpy.NewServer(s.SerialNo, scrcpy.ServerOptions{
		ServerPath:    scrcpyCfg.ServerPath,
		MaxResolution: scrcpyCfg.MaxResolution,
		MaxFPS:        scrcpyCfg.MaxFPS,
		BitRate:       scrcpyCfg.BitRate,
	})
	if err != nil {
		return err
	}

	s.controller = scrcpy.NewController(
		s.scrcpyServer.ControlSocket,
		int32(s.scrcpyServer.VideoWidth),
		int32(s.scrcpyServer.VideoHeight),
	)

	h264Track, track, err := agentwebrtc.NewH264Track()
	if err != nil {
		return err
	}
	s.h264Track = h264Track

	controlChan := make(chan []byte, 100)

	roomCB := &lksdk.RoomCallback{
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
		return err
	}

	if _, err = s.room.LocalParticipant.PublishTrack(track, &lksdk.TrackPublicationOptions{
		Name:        "screen",
		Source:      livekit.TrackSource_SCREEN_SHARE,
		VideoWidth:  s.scrcpyServer.VideoWidth,
		VideoHeight: s.scrcpyServer.VideoHeight,
	}); err != nil {
		return err
	}

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
			return
		}

		isKeyFrame := parser.IsKeyFrame(nalType)

		if err := s.h264Track.FeedNALUnit(nalType, nalData, isKeyFrame); err != nil {
			log.Printf("[%s] feed NAL error: %v", s.SerialNo, err)
		}
	}
}

func (s *Session) Destroy() {
	s.mu.Lock()
	defer s.mu.Unlock()
	defer s.doneOnce.Do(func() {
		close(s.done)
	})

	if s.cancel != nil {
		s.cancel()
		s.cancel = nil
	}
	if s.room != nil {
		s.room.Disconnect()
		s.room = nil
	}
	if s.scrcpyServer != nil {
		s.scrcpyServer.Destroy()
		s.scrcpyServer = nil
	}
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
