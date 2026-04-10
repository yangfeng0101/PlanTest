package harmony

import (
	"context"
	"fmt"
	"os/exec"
	"strconv"
)

// InputManager handles touch and gesture input for HarmonyOS devices
type InputManager struct {
	serial      string
	hdcPath     string
	ctx         context.Context
	screenWidth int
	screenHeight int
}

// NewInputManager creates a new input manager for HarmonyOS device
func NewInputManager(serial string, hdcPath string, screenWidth, screenHeight int) *InputManager {
	return &InputManager{
		serial:       serial,
		hdcPath:      hdcPath,
		ctx:          context.Background(),
		screenWidth:  screenWidth,
		screenHeight: screenHeight,
	}
}

// WithContext sets the context for input operations
func (im *InputManager) WithContext(ctx context.Context) *InputManager {
	im.ctx = ctx
	return im
}

// Tap performs a tap at the specified coordinates
func (im *InputManager) Tap(x, y int) error {
	// HarmonyOS uses uinput for touch events
	// hdc shell sendevent /dev/input/eventX EV_ABS ABS_MT_POSITION_X <x>
	// hdc shell sendevent /dev/input/eventX EV_ABS ABS_MT_POSITION_Y <y>
	// hdc shell sendevent /dev/input/eventX EV_KEY BTN_TOUCH 1
	// hdc shell sendevent /dev/input/eventX EV_SYN SYN_REPORT 0
	// hdc shell sendevent /dev/input/eventX EV_KEY BTN_TOUCH 0
	// hdc shell sendevent /dev/input/eventX EV_SYN SYN_REPORT 0

	// Simplified approach using input tap command (similar to Android)
	cmd := exec.CommandContext(
		im.ctx,
		im.hdcPath,
		"-t", im.serial,
		"shell", "input", "tap",
		strconv.Itoa(x), strconv.Itoa(y),
	)

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("tap failed: %w", err)
	}

	return nil
}

// Swipe performs a swipe gesture from (x1, y1) to (x2, y2)
func (im *InputManager) Swipe(x1, y1, x2, y2 int) error {
	// Default swipe duration: 300ms
	return im.SwipeWithDuration(x1, y1, x2, y2, 300)
}

// SwipeWithDuration performs a swipe gesture with specified duration
func (im *InputManager) SwipeWithDuration(x1, y1, x2, y2, durationMs int) error {
	// hdc shell input swipe <x1> <y1> <x2> <y2> <duration>
	cmd := exec.CommandContext(
		im.ctx,
		im.hdcPath,
		"-t", im.serial,
		"shell", "input", "swipe",
		strconv.Itoa(x1), strconv.Itoa(y1),
		strconv.Itoa(x2), strconv.Itoa(y2),
		strconv.Itoa(durationMs),
	)

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("swipe failed: %w", err)
	}

	return nil
}

// LongPress performs a long press at the specified coordinates
func (im *InputManager) LongPress(x, y int) error {
	// Long press is a swipe with no movement
	return im.SwipeWithDuration(x, y, x, y, 500)
}

// Drag performs a drag gesture (long press + swipe)
func (im *InputManager) Drag(x1, y1, x2, y2 int) error {
	// First long press at start point
	if err := im.LongPress(x1, y1); err != nil {
		return err
	}

	// Then swipe to end point
	return im.Swipe(x1, y1, x2, y2)
}

// Pinch performs a pinch gesture
func (im *InputManager) Pinch(centerX, centerY int, startDistance, endDistance int) error {
	// Pinch requires two simultaneous swipe gestures
	// This is complex to implement with shell commands
	// For now, we'll use a simplified approach

	// Calculate start and end points for two fingers
	halfStart := startDistance / 2
	halfEnd := endDistance / 2

	// Finger 1: moves from (centerX - halfStart) to (centerX - halfEnd)
	// Finger 2: moves from (centerX + halfStart) to (centerX + halfEnd)

	// Note: True pinch requires multi-touch which may need uinput directly
	// This is a placeholder that uses swipe gestures
	return fmt.Errorf("pinch gesture not fully implemented for HarmonyOS")
}

// SendKeyEvent sends a key event
func (im *InputManager) SendKeyEvent(keyCode int) error {
	// hdc shell input keyevent <keyCode>
	cmd := exec.CommandContext(
		im.ctx,
		im.hdcPath,
		"-t", im.serial,
		"shell", "input", "keyevent",
		strconv.Itoa(keyCode),
	)

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("keyevent failed: %w", err)
	}

	return nil
}

// PressHome presses the home button
func (im *InputManager) PressHome() error {
	// Home key code is 3 (same as Android)
	return im.SendKeyEvent(3)
}

// PressBack presses the back button
func (im *InputManager) PressBack() error {
	// Back key code is 4 (same as Android)
	return im.SendKeyEvent(4)
}

// PressPower presses the power button
func (im *InputManager) PressPower() error {
	// Power key code is 26 (same as Android)
	return im.SendKeyEvent(26)
}

// PressVolumeUp presses volume up
func (im *InputManager) PressVolumeUp() error {
	// Volume up key code is 24 (same as Android)
	return im.SendKeyEvent(24)
}

// PressVolumeDown presses volume down
func (im *InputManager) PressVolumeDown() error {
	// Volume down key code is 25 (same as Android)
	return im.SendKeyEvent(25)
}

// TypeText types text using the input method
func (im *InputManager) TypeText(text string) error {
	// hdc shell input text <text>
	cmd := exec.CommandContext(
		im.ctx,
		im.hdcPath,
		"-t", im.serial,
		"shell", "input", "text", text,
	)

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("text input failed: %w", err)
	}

	return nil
}

// ScrollUp scrolls up (swipe from bottom to top)
func (im *InputManager) ScrollUp() error {
	// Swipe from bottom-center to top-center
	x := im.screenWidth / 2
	y1 := int(float64(im.screenHeight) * 0.75) // 75% down
	y2 := int(float64(im.screenHeight) * 0.25) // 25% down
	return im.Swipe(x, y1, x, y2)
}

// ScrollDown scrolls down (swipe from top to bottom)
func (im *InputManager) ScrollDown() error {
	// Swipe from top-center to bottom-center
	x := im.screenWidth / 2
	y1 := int(float64(im.screenHeight) * 0.25) // 25% down
	y2 := int(float64(im.screenHeight) * 0.75) // 75% down
	return im.Swipe(x, y1, x, y2)
}

// ScrollLeft scrolls left (swipe from right to left)
func (im *InputManager) ScrollLeft() error {
	// Swipe from right-center to left-center
	y := im.screenHeight / 2
	x1 := int(float64(im.screenWidth) * 0.75) // 75% right
	x2 := int(float64(im.screenWidth) * 0.25) // 25% right
	return im.Swipe(x1, y, x2, y)
}

// ScrollRight scrolls right (swipe from left to right)
func (im *InputManager) ScrollRight() error {
	// Swipe from left-center to right-center
	y := im.screenHeight / 2
	x1 := int(float64(im.screenWidth) * 0.25) // 25% right
	x2 := int(float64(im.screenWidth) * 0.75) // 75% right
	return im.Swipe(x1, y, x2, y)
}

// ScreenCoordinate converts normalized coordinates (0-1) to screen coordinates
func (im *InputManager) ScreenCoordinate(normX, normY float64) (int, int) {
	x := int(normX * float64(im.screenWidth))
	y := int(normY * float64(im.screenHeight))
	return x, y
}
