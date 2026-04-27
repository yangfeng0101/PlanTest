package webrtc

import (
	"time"

	"github.com/pion/rtp"
	"github.com/pion/rtp/codecs"
	"github.com/pion/webrtc/v4"
	"screen-svc/internal/scrcpy"
)

const (
	h264PayloadType = 102
	h264ClockRate   = 90000 // H.264 标准时钟频率
)

type H264Track struct {
	track      *webrtc.TrackLocalStaticRTP
	packetizer rtp.Packetizer
	parser     *scrcpy.H264Parser
	ssrc       uint32
	lastTime   time.Time
}

func NewH264Track() (*H264Track, *webrtc.TrackLocalStaticRTP, error) {
	track, err := webrtc.NewTrackLocalStaticRTP(
		webrtc.RTPCodecCapability{
			MimeType:    webrtc.MimeTypeH264,
			ClockRate:   h264ClockRate,
			SDPFmtpLine: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=640032",
		},
		"video",
		"linker",
	)
	if err != nil {
		return nil, nil, err
	}

	packetizer := rtp.NewPacketizer(
		1200,
		h264PayloadType,
		uint32(time.Now().UnixNano()),
		&codecs.H264Payloader{},
		rtp.NewRandomSequencer(),
		h264ClockRate,
	)

	return &H264Track{
		track:      track,
		packetizer: packetizer,
	}, track, nil
}

func (t *H264Track) SetParser(p *scrcpy.H264Parser) {
	t.parser = p
}

func (t *H264Track) FeedNALUnit(nalType byte, nalData []byte, isKeyFrame bool) error {
	now := time.Now()
	var duration uint32
	if !t.lastTime.IsZero() {
		delta := now.Sub(t.lastTime)
		duration = uint32(delta.Seconds() * h264ClockRate)
	} else {
		duration = uint32(h264ClockRate / 30)
	}
	t.lastTime = now

	if isKeyFrame && t.parser != nil {
		sps, pps := t.parser.GetSPSAndPPS()
		if sps != nil {
			if err := t.sendNAL(sps, duration, false); err != nil {
				return err
			}
		}
		if pps != nil {
			if err := t.sendNAL(pps, duration, false); err != nil {
				return err
			}
		}
	}

	return t.sendNAL(nalData, duration, true)
}

func (t *H264Track) sendNAL(nalData []byte, duration uint32, marker bool) error {
	packets := t.packetizer.Packetize(nalData, duration)

	if marker && len(packets) > 0 {
		packets[len(packets)-1].Marker = true
	}

	for _, pkt := range packets {
		if err := t.track.WriteRTP(pkt); err != nil {
			return err
		}
	}
	return nil
}
