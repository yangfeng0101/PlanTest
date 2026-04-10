package scrcpy

import (
	"encoding/binary"
	"fmt"
)

// SendTouch sends a touch event to the device
// scrcpy 2.x touch message format (28 bytes):
// type(1) + action(1) + pointer_id(8) + x(4) + y(4) + screen_width(4) + screen_height(4) + pressure(2) + buttons(4)
func (p *Process) SendTouch(x, y int, action byte, screenWidth, screenHeight int) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, TouchMessageSize)
	msg[0] = ControlMsgTypeInjectTouch
	msg[1] = action
	// pointer_id (8 bytes, big endian) - using 0 for single touch
	binary.BigEndian.PutUint64(msg[2:10], 0)
	// x position (4 bytes)
	binary.BigEndian.PutUint32(msg[10:14], uint32(x))
	// y position (4 bytes)
	binary.BigEndian.PutUint32(msg[14:18], uint32(y))
	// screen width (4 bytes)
	binary.BigEndian.PutUint32(msg[18:22], uint32(screenWidth))
	// screen height (4 bytes)
	binary.BigEndian.PutUint32(msg[22:26], uint32(screenHeight))
	// pressure (2 bytes) - 0xFFFF for full pressure
	binary.BigEndian.PutUint16(msg[26:28], 0xFFFF)

	_, err := p.stdin.Write(msg)
	return err
}

// SendTouchWithPressure sends a touch event with custom pressure
func (p *Process) SendTouchWithPressure(x, y int, action byte, pressure uint16, screenWidth, screenHeight int) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, TouchMessageSize)
	msg[0] = ControlMsgTypeInjectTouch
	msg[1] = action
	binary.BigEndian.PutUint64(msg[2:10], 0)
	binary.BigEndian.PutUint32(msg[10:14], uint32(x))
	binary.BigEndian.PutUint32(msg[14:18], uint32(y))
	binary.BigEndian.PutUint32(msg[18:22], uint32(screenWidth))
	binary.BigEndian.PutUint32(msg[22:26], uint32(screenHeight))
	binary.BigEndian.PutUint16(msg[26:28], pressure)

	_, err := p.stdin.Write(msg)
	return err
}

// SendKey sends a key event to the device
// scrcpy 2.x key message format (14 bytes):
// type(1) + action(1) + keycode(4) + repeat(4) + metastate(4)
func (p *Process) SendKey(keyCode int, action byte) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, KeyMessageSize)
	msg[0] = ControlMsgTypeInjectKeycode
	msg[1] = action
	binary.BigEndian.PutUint32(msg[2:6], uint32(keyCode))
	binary.BigEndian.PutUint32(msg[6:10], 0)  // repeat count
	binary.BigEndian.PutUint32(msg[10:14], 0) // metastate

	_, err := p.stdin.Write(msg)
	return err
}

// SendKeyWithMeta sends a key event with modifier keys
func (p *Process) SendKeyWithMeta(keyCode int, action byte, metastate uint32) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, KeyMessageSize)
	msg[0] = ControlMsgTypeInjectKeycode
	msg[1] = action
	binary.BigEndian.PutUint32(msg[2:6], uint32(keyCode))
	binary.BigEndian.PutUint32(msg[6:10], 0)
	binary.BigEndian.PutUint32(msg[10:14], metastate)

	_, err := p.stdin.Write(msg)
	return err
}

// SendText sends text input to the device
// scrcpy 2.x text message format:
// type(1) + length(4) + text(length bytes)
func (p *Process) SendText(text string) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	length := len(text)
	msg := make([]byte, TextMessageHeaderSize+length)
	msg[0] = ControlMsgTypeInjectText
	binary.BigEndian.PutUint32(msg[1:5], uint32(length))
	copy(msg[5:], text)

	_, err := p.stdin.Write(msg)
	return err
}

// SendScroll sends a scroll event to the device
// scrcpy 2.x scroll message format (21 bytes):
// type(1) + x(4) + y(4) + width(4) + height(4) + dx(4) + dy(4)
func (p *Process) SendScroll(x, y, dx, dy int, screenWidth, screenHeight int) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, ScrollMessageSize)
	msg[0] = ControlMsgTypeInjectScroll
	binary.BigEndian.PutUint32(msg[1:5], uint32(x))
	binary.BigEndian.PutUint32(msg[5:9], uint32(y))
	binary.BigEndian.PutUint32(msg[9:13], uint32(screenWidth))
	binary.BigEndian.PutUint32(msg[13:17], uint32(screenHeight))
	binary.BigEndian.PutUint32(msg[17:21], uint32(dx))
	binary.BigEndian.PutUint32(msg[21:25], uint32(dy))

	_, err := p.stdin.Write(msg)
	return err
}

// SendBack sends the back key
func (p *Process) SendBack() error {
	if err := p.SendKey(KeycodeBack, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeBack, KeyActionUp)
}

// SendHome sends the home key
func (p *Process) SendHome() error {
	if err := p.SendKey(KeycodeHome, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeHome, KeyActionUp)
}

// SendPower sends the power key
func (p *Process) SendPower() error {
	if err := p.SendKey(KeycodePower, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodePower, KeyActionUp)
}

// SendVolumeUp sends volume up key
func (p *Process) SendVolumeUp() error {
	if err := p.SendKey(KeycodeVolumeUp, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeVolumeUp, KeyActionUp)
}

// SendVolumeDown sends volume down key
func (p *Process) SendVolumeDown() error {
	if err := p.SendKey(KeycodeVolumeDown, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeVolumeDown, KeyActionUp)
}

// SendMenu sends the menu key
func (p *Process) SendMenu() error {
	if err := p.SendKey(KeycodeMenu, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeMenu, KeyActionUp)
}

// SendAppSwitch sends the app switch key (recent apps)
func (p *Process) SendAppSwitch() error {
	if err := p.SendKey(KeycodeAppSwitch, KeyActionDown); err != nil {
		return err
	}
	return p.SendKey(KeycodeAppSwitch, KeyActionUp)
}

// SendRotateDevice sends a rotate device command
func (p *Process) SendRotateDevice() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, 1)
	msg[0] = ControlMsgTypeRotateDevice

	_, err := p.stdin.Write(msg)
	return err
}

// SendExpandPanel sends expand notification panel command
func (p *Process) SendExpandPanel() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, 1)
	msg[0] = ControlMsgTypeExpandPanel

	_, err := p.stdin.Write(msg)
	return err
}

// SendCollapsePanel sends collapse notification panel command
func (p *Process) SendCollapsePanel() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.stdin == nil {
		return fmt.Errorf("scrcpy process not running")
	}

	msg := make([]byte, 1)
	msg[0] = ControlMsgTypeCollapsePanel

	_, err := p.stdin.Write(msg)
	return err
}

// Tap performs a tap at the given coordinates
func (p *Process) Tap(x, y int, screenWidth, screenHeight int) error {
	if err := p.SendTouch(x, y, ActionDown, screenWidth, screenHeight); err != nil {
		return err
	}
	return p.SendTouch(x, y, ActionUp, screenWidth, screenHeight)
}

// Swipe performs a swipe from (x1, y1) to (x2, y2) over the given duration (ms)
func (p *Process) Swipe(x1, y1, x2, y2, durationMs int, screenWidth, screenHeight int) error {
	// Calculate steps based on duration (roughly 60fps)
	steps := durationMs * 60 / 1000
	if steps < 1 {
		steps = 1
	}
	if steps > 100 {
		steps = 100
	}

	// Send down event
	if err := p.SendTouch(x1, y1, ActionDown, screenWidth, screenHeight); err != nil {
		return err
	}

	// Send move events
	for i := 1; i <= steps; i++ {
		t := float64(i) / float64(steps)
		x := int(float64(x1) + t*float64(x2-x1))
		y := int(float64(y1) + t*float64(y2-y1))
		if err := p.SendTouch(x, y, ActionMove, screenWidth, screenHeight); err != nil {
			return err
		}
	}

	// Send up event
	return p.SendTouch(x2, y2, ActionUp, screenWidth, screenHeight)
}

// LongPress performs a long press at the given coordinates
func (p *Process) LongPress(x, y, durationMs int, screenWidth, screenHeight int) error {
	if err := p.SendTouch(x, y, ActionDown, screenWidth, screenHeight); err != nil {
		return err
	}
	// Wait for duration
	// Note: In production, this should be done asynchronously
	// For now, the caller should handle timing
	return p.SendTouch(x, y, ActionUp, screenWidth, screenHeight)
}
