package scrcpy

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net"
)

type ControlMsg struct {
	Type    string `json:"type"`
	Action  string `json:"action"`
	X       int32  `json:"x"`
	Y       int32  `json:"y"`
	KeyCode int32  `json:"keyCode"`
	Text    string `json:"text"`
}

type Controller struct {
	conn         net.Conn
	DeviceWidth  int32
	DeviceHeight int32
}

func NewController(conn net.Conn, w, h int32) *Controller {
	return &Controller{conn: conn, DeviceWidth: w, DeviceHeight: h}
}

func (c *Controller) HandleDataChannelMsg(raw []byte) error {
	var msg ControlMsg
	if err := json.Unmarshal(raw, &msg); err != nil {
		return err
	}

	switch msg.Type {
	case "touch":
		return c.sendTouchEvent(msg)
	case "key":
		return c.sendKeyEvent(msg)
	case "text":
		return c.sendTextEvent(msg.Text)
	case "back":
		return c.sendKeyEvent(ControlMsg{Action: "down", KeyCode: 4})
	case "home":
		return c.sendKeyEvent(ControlMsg{Action: "down", KeyCode: 3})
	}
	return fmt.Errorf("unsupported control message type %q", msg.Type)
}

func (c *Controller) sendTouchEvent(msg ControlMsg) error {
	if c.conn == nil {
		return fmt.Errorf("control socket is not connected")
	}
	if msg.Action != "down" && msg.Action != "up" && msg.Action != "move" {
		return fmt.Errorf("unsupported touch action %q", msg.Action)
	}
	if msg.X < 0 {
		msg.X = 0
	}
	if msg.Y < 0 {
		msg.Y = 0
	}
	if msg.X > c.DeviceWidth {
		msg.X = c.DeviceWidth
	}
	if msg.Y > c.DeviceHeight {
		msg.Y = c.DeviceHeight
	}

	buf := make([]byte, 32)
	buf[0] = 2

	switch msg.Action {
	case "down":
		buf[1] = 0
	case "up":
		buf[1] = 1
	case "move":
		buf[1] = 2
	}

	binary.BigEndian.PutUint64(buf[2:], 0xFFFFFFFFFFFFFFFF)
	binary.BigEndian.PutUint32(buf[10:], uint32(msg.X))
	binary.BigEndian.PutUint32(buf[14:], uint32(msg.Y))
	binary.BigEndian.PutUint16(buf[18:], uint16(c.DeviceWidth))
	binary.BigEndian.PutUint16(buf[20:], uint16(c.DeviceHeight))
	binary.BigEndian.PutUint16(buf[22:], 0xFFFF)
	binary.BigEndian.PutUint32(buf[24:], 1)
	binary.BigEndian.PutUint32(buf[28:], 1)

	_, err := c.conn.Write(buf)
	return err
}

func (c *Controller) sendKeyEvent(msg ControlMsg) error {
	if c.conn == nil {
		return fmt.Errorf("control socket is not connected")
	}
	if msg.KeyCode <= 0 {
		return fmt.Errorf("invalid key code %d", msg.KeyCode)
	}

	buf := make([]byte, 14)
	buf[0] = 0

	switch msg.Action {
	case "down":
		buf[1] = 0
	case "up":
		buf[1] = 1
	default:
		buf[1] = 0
	}

	binary.BigEndian.PutUint32(buf[2:], uint32(msg.KeyCode))
	binary.BigEndian.PutUint32(buf[6:], 0)
	binary.BigEndian.PutUint32(buf[10:], 0)

	_, err := c.conn.Write(buf)
	return err
}

func (c *Controller) sendTextEvent(text string) error {
	if c.conn == nil {
		return fmt.Errorf("control socket is not connected")
	}
	if text == "" {
		return nil
	}

	textBytes := []byte(text)
	buf := make([]byte, 5+len(textBytes))
	buf[0] = 1
	binary.BigEndian.PutUint32(buf[1:], uint32(len(textBytes)))
	copy(buf[5:], textBytes)
	_, err := c.conn.Write(buf)
	return err
}
