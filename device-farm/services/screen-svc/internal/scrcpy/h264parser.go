package scrcpy

import (
	"bytes"
	"io"
)

// NAL Unit 类型定义
const (
	NALTypeSliceNonIDR = 1 // P帧
	NALTypeSliceIDR    = 5 // I帧（关键帧）
	NALTypeSPS         = 7 // 序列参数集
	NALTypePPS         = 8 // 图像参数集
)

var startCode = []byte{0x00, 0x00, 0x00, 0x01}
var shortStartCode = []byte{0x00, 0x00, 0x01}

// H264Parser 从 scrcpy 输出流中解析 NAL Units
type H264Parser struct {
	reader io.Reader
	buf    []byte
	sps    []byte // 缓存 SPS，IDR 帧前需要重新发送
	pps    []byte // 缓存 PPS
}

func NewH264Parser(r io.Reader) *H264Parser {
	return &H264Parser{
		reader: r,
		buf:    make([]byte, 0, 1024*1024), // 1MB 初始缓冲
	}
}

func findStartCode(b []byte) (int, int) {
	idx3 := bytes.Index(b, shortStartCode)
	if idx3 < 0 {
		return -1, 0
	}
	if idx3 > 0 && b[idx3-1] == 0x00 {
		return idx3 - 1, 4
	}
	return idx3, 3
}

// ReadNALUnit 读取下一个完整的 NAL Unit
func (p *H264Parser) ReadNALUnit() (nalType byte, data []byte, err error) {
	chunk := make([]byte, 65536)

	for {
		idx, startLen := findStartCode(p.buf)
		if idx < 0 {
			n, readErr := p.reader.Read(chunk)
			if n > 0 {
				p.buf = append(p.buf, chunk[:n]...)
			}
			if readErr != nil {
				return 0, nil, readErr
			}
			continue
		}

		nalStart := idx + startLen
		remaining := p.buf[nalStart:]

		nextIdx, _ := findStartCode(remaining)
		if nextIdx < 0 {
			n, readErr := p.reader.Read(chunk)
			if n > 0 {
				p.buf = append(p.buf, chunk[:n]...)
			}
			if readErr != nil && readErr != io.EOF {
				return 0, nil, readErr
			}
			if readErr == io.EOF && len(remaining) > 0 {
				nalData := make([]byte, len(remaining))
				copy(nalData, remaining)
				p.buf = p.buf[:0]
				nalType = nalData[0] & 0x1F
				return nalType, nalData, nil
			}
			continue
		}

		nalData := make([]byte, nextIdx)
		copy(nalData, remaining[:nextIdx])
		p.buf = p.buf[nalStart+nextIdx:]

		nalType = nalData[0] & 0x1F

		switch nalType {
		case NALTypeSPS:
			p.sps = append([]byte(nil), nalData...)
		case NALTypePPS:
			p.pps = append([]byte(nil), nalData...)
		}

		return nalType, nalData, nil
	}
}

func (p *H264Parser) IsKeyFrame(nalType byte) bool {
	return nalType == NALTypeSliceIDR
}

func (p *H264Parser) GetSPSAndPPS() (sps, pps []byte) {
	return p.sps, p.pps
}
