package video

import (
	"fmt"

	"github.com/pion/rtp"
)

const (
	// MTU is the maximum transmission unit for RTP packets
	MTU = 1200

	// ClockRate for H.264 video
	ClockRate = 90000

	// DefaultPayloadType for H.264
	DefaultPayloadType = 96

	// FU-A indicator and header types
	fuaIndicator = 28
	fuaHeader    = 28

	// NAL type mask
	nalTypeMask = 0x1F

	// FU-A header flags
	fuStart = 0x80
	fuEnd   = 0x40
)

// RTPPacker packs H.264 NAL units into RTP packets
type RTPPacker struct {
	sequenceNumber uint16
	ssrc           uint32
	payloadType    uint8
	timestamp      uint32
}

// NewRTPPacker creates a new RTP packer
func NewRTPPacker() *RTPPacker {
	return &RTPPacker{
		sequenceNumber: 0,
		ssrc:           0, // Will be set by WebRTC
		payloadType:    DefaultPayloadType,
		timestamp:      0,
	}
}

// SetSSRC sets the SSRC for generated packets
func (p *RTPPacker) SetSSRC(ssrc uint32) {
	p.ssrc = ssrc
}

// SetPayloadType sets the payload type
func (p *RTPPacker) SetPayloadType(pt uint8) {
	p.payloadType = pt
}

// Pack packs a NAL unit into one or more RTP packets
// Returns a slice of RTP packets (single packet or FU-A fragments)
func (p *RTPPacker) Pack(nalUnit []byte, timestamp uint32) []*rtp.Packet {
	if len(nalUnit) == 0 {
		return nil
	}

	p.timestamp = timestamp

	// Single NAL Unit Packet (<= MTU bytes)
	if len(nalUnit) <= MTU {
		return p.packSingleNAL(nalUnit)
	}

	// FU-A fragmentation (> MTU bytes)
	return p.packFUA(nalUnit)
}

// packSingleNAL creates a single NAL unit RTP packet
func (p *RTPPacker) packSingleNAL(nalUnit []byte) []*rtp.Packet {
	// Handle sequence number wraparound (uint16)
	p.sequenceNumber = (p.sequenceNumber + 1) & 0xFFFF

	packet := &rtp.Packet{
		Header: rtp.Header{
			Version:        2,
			Padding:        false,
			Extension:      false,
			Marker:         true, // Last packet of frame
			PayloadType:    p.payloadType,
			SequenceNumber: p.sequenceNumber,
			Timestamp:      p.timestamp,
			SSRC:           p.ssrc,
		},
		Payload: nalUnit,
	}

	return []*rtp.Packet{packet}
}

// packFUA creates FU-A fragmented RTP packets
func (p *RTPPacker) packFUA(nalUnit []byte) []*rtp.Packet {
	nalType := nalUnit[0] & nalTypeMask
	nalRefIdc := nalUnit[0] & 0x60 // nal_ref_idc bits

	// Remove NAL header for fragmentation
	nalBody := nalUnit[1:]
	bodyLen := len(nalBody)

	// Calculate number of fragments
	maxFragmentLen := MTU - 2 // 2 bytes for FU-A indicator and header
	numFragments := (bodyLen + maxFragmentLen - 1) / maxFragmentLen

	packets := make([]*rtp.Packet, 0, numFragments)

	// Fragment the NAL unit
	offset := 0
	for offset < bodyLen {
		// Calculate fragment length
		fragLen := bodyLen - offset
		if fragLen > maxFragmentLen {
			fragLen = maxFragmentLen
		}

		// Build FU-A indicator: nal_ref_idc | 28 (FU-A type)
		indicator := nalRefIdc | fuaIndicator

		// Build FU-A header
		header := byte(nalType)
		if offset == 0 {
			header |= fuStart // Start bit
		}
		if offset+fragLen >= bodyLen {
			header |= fuEnd // End bit
		}

		// Create payload: indicator + header + fragment
		payload := make([]byte, 2+fragLen)
		payload[0] = indicator
		payload[1] = header
		copy(payload[2:], nalBody[offset:offset+fragLen])

		// Handle sequence number wraparound (uint16)
		p.sequenceNumber = (p.sequenceNumber + 1) & 0xFFFF

		// Marker bit set on last fragment
		marker := offset+fragLen >= bodyLen

		packet := &rtp.Packet{
			Header: rtp.Header{
				Version:        2,
				Padding:        false,
				Extension:      false,
				Marker:         marker,
				PayloadType:    p.payloadType,
				SequenceNumber: p.sequenceNumber,
				Timestamp:      p.timestamp,
				SSRC:           p.ssrc,
			},
			Payload: payload,
		}

		packets = append(packets, packet)
		offset += fragLen
	}

	return packets
}

// PackWithSPSPPS packs NAL unit with SPS/PPS prefix (for keyframes)
func (p *RTPPacker) PackWithSPSPPS(nalUnit, sps, pps []byte, timestamp uint32) []*rtp.Packet {
	var packets []*rtp.Packet

	// Pack SPS first
	if len(sps) > 0 {
		packets = append(packets, p.Pack(sps, timestamp)...)
	}

	// Pack PPS second
	if len(pps) > 0 {
		packets = append(packets, p.Pack(pps, timestamp)...)
	}

	// Pack the main NAL unit
	packets = append(packets, p.Pack(nalUnit, timestamp)...)

	// Set marker bit on last packet
	if len(packets) > 0 {
		packets[len(packets)-1].Header.Marker = true
	}

	return packets
}

// CalculateTimestamp calculates RTP timestamp from frame number and frame rate
func CalculateTimestamp(frameNum int, fps int) uint32 {
	// RTP timestamp = frame number * clock rate / fps
	return uint32(uint64(frameNum) * ClockRate / uint64(fps))
}

// ValidateH264Packet validates an H.264 RTP packet
func ValidateH264Packet(packet *rtp.Packet) error {
	if len(packet.Payload) == 0 {
		return fmt.Errorf("empty payload")
	}

	nalType := packet.Payload[0] & nalTypeMask

	// Check for single NAL unit or FU-A
	if nalType >= 1 && nalType <= 23 {
		// Single NAL unit packet
		return nil
	}

	if nalType == 28 {
		// FU-A packet, need at least 2 bytes
		if len(packet.Payload) < 2 {
			return fmt.Errorf("invalid FU-A packet: too short")
		}
		return nil
	}

	return fmt.Errorf("unsupported NAL type: %d", nalType)
}
