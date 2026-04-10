package video

import (
	"bytes"
	"encoding/binary"
	"fmt"
)

// NALUnitType represents the type of a NAL unit
type NALUnitType uint8

const (
	NALTypeNonIDR    NALUnitType = 1  // Non-IDR slice
	NALTypeIDR       NALUnitType = 5  // IDR slice
	NALTypeSEI       NALUnitType = 6  // Supplemental enhancement information
	NALTypeSPS       NALUnitType = 7  // Sequence parameter set
	NALTypePPS       NALUnitType = 8  // Picture parameter set
	NALTypeAUD       NALUnitType = 9  // Access unit delimiter
)

// NALUnit represents a parsed NAL unit
type NALUnit struct {
	Type     NALUnitType
	Data     []byte
	RefIdc   uint8
}

// NALParser parses H.264 NAL units from a byte stream
type NALParser struct {
	spsCache []byte
	ppsCache []byte
}

// NewNALParser creates a new NAL parser
func NewNALParser() *NALParser {
	return &NALParser{}
}

// Parse parses H.264 data and extracts NAL units
// Supports both Annex B format (start codes) and AVCC format (length-prefixed)
func (p *NALParser) Parse(data []byte) ([]NALUnit, error) {
	if len(data) == 0 {
		return nil, nil
	}

	// Check for Annex B start code (0x00 0x00 0x01 or 0x00 0x00 0x00 0x01)
	if bytes.HasPrefix(data, []byte{0x00, 0x00, 0x01}) ||
		bytes.HasPrefix(data, []byte{0x00, 0x00, 0x00, 0x01}) ||
		bytes.Contains(data, []byte{0x00, 0x00, 0x01}) {
		return p.parseAnnexB(data)
	}

	// Try AVCC format (length-prefixed)
	return p.parseAVCC(data)
}

// parseAnnexB parses Annex B format H.264 stream
func (p *NALParser) parseAnnexB(data []byte) ([]NALUnit, error) {
	var units []NALUnit

	// Find all start code positions
	// Start codes can be 3 bytes (0x00 0x00 0x01) or 4 bytes (0x00 0x00 0x00 0x01)
	startCodes := p.findStartCodes(data)

	if len(startCodes) == 0 {
		// No start codes found, treat entire data as single NAL unit
		if len(data) > 0 {
			unit, err := p.parseNALHeader(data)
			if err != nil {
				return nil, err
			}
			units = append(units, unit)
		}
		return units, nil
	}

	// Extract NAL units between start codes
	for i := 0; i < len(startCodes); i++ {
		start := startCodes[i]

		// Find the end of this NAL unit (next start code or end of data)
		end := len(data)
		if i < len(startCodes)-1 {
			// Move back to find the actual start of next NAL
			nextStart := startCodes[i+1]
			// Account for possible 4-byte start code
			for nextStart > 0 && data[nextStart-1] == 0 {
				nextStart--
			}
			end = nextStart
		}

		// Skip the start code itself (3 or 4 bytes)
		nalStart := start
		if start+3 <= len(data) && data[start] == 0 && data[start+1] == 0 && data[start+2] == 0 && data[start+3] == 1 {
			nalStart = start + 4
		} else if start+2 <= len(data) && data[start] == 0 && data[start+1] == 0 && data[start+2] == 1 {
			nalStart = start + 3
		}

		if nalStart >= end {
			continue
		}

		nalData := data[nalStart:end]
		if len(nalData) == 0 {
			continue
		}

		unit, err := p.parseNALHeader(nalData)
		if err != nil {
			continue // Skip malformed NAL units
		}
		units = append(units, unit)
	}

	return units, nil
}

// parseAVCC parses AVCC format (length-prefixed) H.264 stream
func (p *NALParser) parseAVCC(data []byte) ([]NALUnit, error) {
	var units []NALUnit

	offset := 0
	for offset < len(data) {
		// Need at least 4 bytes for length prefix
		if offset+4 > len(data) {
			break
		}

		// Read 4-byte big-endian length
		nalLength := int(binary.BigEndian.Uint32(data[offset : offset+4]))
		offset += 4

		// Validate NAL length
		if offset+nalLength > len(data) {
			return nil, fmt.Errorf("NAL length %d exceeds remaining data", nalLength)
		}

		nalData := data[offset : offset+nalLength]
		offset += nalLength

		unit, err := p.parseNALHeader(nalData)
		if err != nil {
			continue
		}
		units = append(units, unit)
	}

	return units, nil
}

// parseNALHeader parses NAL header and creates NALUnit
func (p *NALParser) parseNALHeader(data []byte) (NALUnit, error) {
	if len(data) == 0 {
		return NALUnit{}, fmt.Errorf("empty NAL data")
	}

	// NAL header byte: forbidden_zero_bit(1) | nal_ref_idc(2) | nal_unit_type(5)
	header := data[0]
	refIdc := (header >> 5) & 0x03
	nalType := NALUnitType(header & 0x1F)

	return NALUnit{
		Type:   nalType,
		Data:   data,
		RefIdc: refIdc,
	}, nil
}

// findStartCodes finds positions of Annex B start codes in the data
func (p *NALParser) findStartCodes(data []byte) []int {
	var positions []int

	for i := 0; i < len(data)-2; i++ {
		// Check for 3-byte start code
		if data[i] == 0 && data[i+1] == 0 && data[i+2] == 1 {
			positions = append(positions, i)
			i += 2 // Skip ahead
		}
	}

	return positions
}

// ExtractSPSPPS extracts and caches SPS and PPS NAL units
func (p *NALParser) ExtractSPSPPS(units []NALUnit) {
	for _, unit := range units {
		switch unit.Type {
		case NALTypeSPS:
			p.spsCache = unit.Data
		case NALTypePPS:
			p.ppsCache = unit.Data
		}
	}
}

// GetSPS returns cached SPS data
func (p *NALParser) GetSPS() []byte {
	return p.spsCache
}

// GetPPS returns cached PPS data
func (p *NALParser) GetPPS() []byte {
	return p.ppsCache
}

// HasSPSPPS returns true if both SPS and PPS have been cached
func (p *NALParser) HasSPSPPS() bool {
	return len(p.spsCache) > 0 && len(p.ppsCache) > 0
}

// IsKeyFrame checks if the NAL units contain an IDR frame
func (p *NALParser) IsKeyFrame(units []NALUnit) bool {
	for _, unit := range units {
		if unit.Type == NALTypeIDR {
			return true
		}
	}
	return false
}

// GetTypeString returns a string representation of NAL unit type
func (t NALUnitType) String() string {
	switch t {
	case NALTypeNonIDR:
		return "Non-IDR"
	case NALTypeIDR:
		return "IDR"
	case NALTypeSEI:
		return "SEI"
	case NALTypeSPS:
		return "SPS"
	case NALTypePPS:
		return "PPS"
	case NALTypeAUD:
		return "AUD"
	default:
		return fmt.Sprintf("Unknown(%d)", t)
	}
}
