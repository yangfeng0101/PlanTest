package scrcpy

// Control message types for scrcpy 2.x protocol
// Reference: https://github.com/Genymobile/scrcpy/blob/master/app/src/control_msg.h
const (
	ControlMsgTypeInjectKeycode    = 0
	ControlMsgTypeInjectText       = 1
	ControlMsgTypeInjectTouch      = 2
	ControlMsgTypeInjectScroll     = 3
	ControlMsgTypeBackOrScreenOn   = 4
	ControlMsgTypeExpandPanel      = 5
	ControlMsgTypeCollapsePanel    = 6
	ControlMsgTypeGetClipboard     = 7
	ControlMsgTypeSetClipboard     = 8
	ControlMsgTypeSetScreenPower   = 9
	ControlMsgTypeRotateDevice     = 10
)

// Touch action types
const (
	ActionDown = 0
	ActionUp   = 1
	ActionMove = 2
)

// Key action types
const (
	KeyActionDown = 0
	KeyActionUp   = 1
)

// Android keycodes (common ones)
// Full list: https://developer.android.com/reference/android/view/KeyEvent
const (
	KeycodeUnknown    = 0
	KeycodeSoftLeft   = 1
	KeycodeSoftRight  = 2
	KeycodeHome       = 3
	KeycodeBack       = 4
	KeycodeCall       = 5
	KeycodeEndcall    = 6
	Keycode0          = 7
	Keycode1          = 8
	Keycode2          = 9
	Keycode3          = 10
	Keycode4          = 11
	Keycode5          = 12
	Keycode6          = 13
	Keycode7          = 14
	Keycode8          = 15
	Keycode9          = 16
	KeycodeStar       = 17
	KeycodePound      = 18
	KeycodeDpadUp     = 19
	KeycodeDpadDown   = 20
	KeycodeDpadLeft   = 21
	KeycodeDpadRight  = 22
	KeycodeDpadCenter = 23
	KeycodeVolumeUp   = 24
	KeycodeVolumeDown = 25
	KeycodePower      = 26
	KeycodeCamera     = 27
	KeycodeClear      = 28
	KeycodeA          = 29
	KeycodeB          = 30
	KeycodeC          = 31
	KeycodeD          = 32
	KeycodeE          = 33
	KeycodeF          = 34
	KeycodeG          = 35
	KeycodeH          = 36
	KeycodeI          = 37
	KeycodeJ          = 38
	KeycodeK          = 39
	KeycodeL          = 40
	KeycodeM          = 41
	KeycodeN          = 42
	KeycodeO          = 43
	KeycodeP          = 44
	KeycodeQ          = 45
	KeycodeR          = 46
	KeycodeS          = 47
	KeycodeT          = 48
	KeycodeU          = 49
	KeycodeV          = 50
	KeycodeW          = 51
	KeycodeX          = 52
	KeycodeY          = 53
	KeycodeZ          = 54
	KeycodeComma      = 55
	KeycodePeriod     = 56
	KeycodeAltLeft    = 57
	KeycodeAltRight   = 58
	KeycodeShiftLeft  = 59
	KeycodeShiftRight = 60
	KeycodeTab        = 61
	KeycodeSpace      = 62
	KeycodeSym        = 63
	KeycodeExplorer   = 64
	KeycodeEnvelope   = 65
	KeycodeEnter      = 66
	KeycodeDel        = 67  // Backspace
	KeycodeGrave      = 68  // `
	KeycodeMinus      = 69
	KeycodeEquals     = 70
	KeycodeLeftBracket  = 71
	KeycodeRightBracket = 72
	KeycodeBackslash  = 73
	KeycodeSemicolon  = 74
	KeycodeApostrophe = 75
	KeycodeSlash      = 76
	KeycodeAt         = 77
	KeycodeNum        = 78
	KeycodeHeadsethook = 79
	KeycodeFocus      = 80
	KeycodePlus       = 81
	KeycodeMenu       = 82
	KeycodeNotification = 83
	KeycodeSearch     = 84
	KeycodeMediaPlayPause = 85
	KeycodeMediaStop  = 86
	KeycodeMediaNext  = 87
	KeycodeMediaPrevious = 88
	KeycodeMediaRewind = 89
	KeycodeMediaFastForward = 90
	KeycodeMute       = 91
	KeycodePageUp     = 92
	KeycodePageDown   = 93
	KeycodePictsymbols = 94
	KeycodeSwitchCharset = 95
	KeycodeButtonA    = 96
	KeycodeButtonB    = 97
	KeycodeButtonC    = 98
	KeycodeButtonX    = 99
	KeycodeButtonY    = 100
	KeycodeButtonZ    = 101
	KeycodeButtonL1   = 102
	KeycodeButtonR1   = 103
	KeycodeButtonL2   = 104
	KeycodeButtonR2   = 105
	KeycodeButtonThumbl = 106
	KeycodeButtonThumbr = 107
	KeycodeButtonStart  = 108
	KeycodeButtonSelect = 109
	KeycodeButtonMode   = 110
	KeycodeEscape       = 111
	KeycodeForwardDel   = 112  // Delete
	KeycodeCtrlLeft     = 113
	KeycodeCtrlRight    = 114
	KeycodeCapsLock     = 115
	KeycodeScrollLock   = 116
	KeycodeMetaLeft     = 117
	KeycodeMetaRight    = 118
	KeycodeFunction     = 119
	KeycodeSysrq        = 120
	KeycodeBreak        = 121
	KeycodeMoveHome     = 122
	KeycodeMoveEnd      = 123
	KeycodeInsert       = 124
	KeycodeForward      = 125
	KeycodeMediaPlay    = 126
	KeycodeMediaPause   = 127
	KeycodeMediaClose   = 128
	KeycodeMediaEject   = 129
	KeycodeMediaRecord  = 130
	KeycodeF1           = 131
	KeycodeF2           = 132
	KeycodeF3           = 133
	KeycodeF4           = 134
	KeycodeF5           = 135
	KeycodeF6           = 136
	KeycodeF7           = 137
	KeycodeF8           = 138
	KeycodeF9           = 139
	KeycodeF10          = 140
	KeycodeF11          = 141
	KeycodeF12          = 142
	KeycodeNumLock      = 143
	KeycodeNumpad0      = 144
	KeycodeNumpad1      = 145
	KeycodeNumpad2      = 146
	KeycodeNumpad3      = 147
	KeycodeNumpad4      = 148
	KeycodeNumpad5      = 149
	KeycodeNumpad6      = 150
	KeycodeNumpad7      = 151
	KeycodeNumpad8      = 152
	KeycodeNumpad9      = 153
	KeycodeNumpadDivide   = 154
	KeycodeNumpadMultiply = 155
	KeycodeNumpadSubtract = 156
	KeycodeNumpadAdd      = 157
	KeycodeNumpadDot      = 158
	KeycodeNumpadComma    = 159
	KeycodeNumpadEnter    = 160
	KeycodeNumpadEquals   = 161
	KeycodeNumpadLeftParen  = 162
	KeycodeNumpadRightParen = 163
	KeycodeVolumeMute      = 164
	KeycodeInfo            = 165
	KeycodeChannelUp       = 166
	KeycodeChannelDown     = 167
	KeycodeZoomIn          = 168
	KeycodeZoomOut         = 169
	KeycodeTv              = 170
	KeycodeWindow          = 171
	KeycodeGuide           = 172
	KeycodeDvr             = 173
	KeycodeBookmark        = 174
	KeycodeCaptions        = 175
	KeycodeSettings        = 176
	KeycodeTvPower         = 177
	KeycodeTvInput         = 178
	KeycodeStbPower       = 179
	KeycodeStbInput       = 180
	KeycodeAvrPower       = 181
	KeycodeAvrInput       = 182
	KeycodeProgRed        = 183
	KeycodeProgGreen      = 184
	KeycodeProgYellow     = 185
	KeycodeProgBlue       = 186
	KeycodeAppSwitch      = 187
	KeycodeButton1        = 188
	KeycodeButton2        = 189
	KeycodeButton3        = 190
	KeycodeButton4        = 191
	KeycodeButton5        = 192
	KeycodeButton6        = 193
	KeycodeButton7        = 194
	KeycodeButton8        = 195
	KeycodeButton9        = 196
	KeycodeButton10       = 197
	KeycodeButton11       = 198
	KeycodeButton12       = 199
	KeycodeButton13       = 200
	KeycodeButton14       = 201
	KeycodeButton15       = 202
	KeycodeButton16       = 203
	KeycodeLanguageSwitch = 204
	KeycodeMannerMode     = 205
	Keycode3dMode         = 206
	KeycodeContacts       = 207
	KeycodeCalendar       = 208
	KeycodeMusic          = 209
	KeycodeCalculator     = 210
)

// Meta state flags (modifiers)
const (
	MetaNone       = 0
	MetaAltLeft    = 0x02
	MetaAltRight   = 0x04
	MetaShiftLeft  = 0x01
	MetaShiftRight = 0x20
	MetaSym        = 0x04
	MetaFunction   = 0x08
	MetaCtrlLeft   = 0x1000
	MetaCtrlRight  = 0x2000
	MetaMetaLeft   = 0x10000
	MetaMetaRight  = 0x20000
	MetaCapsLock   = 0x100000
	MetaNumLock    = 0x200000
	MetaScrollLock = 0x400000
)

// Touch message size for scrcpy 2.x
// type(1) + action(1) + pointer_id(8) + position(8) + dimensions(8) + pressure(2) = 28 bytes
const TouchMessageSize = 28

// Key message size for scrcpy 2.x
// type(1) + action(1) + keycode(4) + repeat(4) + metastate(4) = 14 bytes
const KeyMessageSize = 14

// Text message header size
// type(1) + length(4) = 5 bytes + text length
const TextMessageHeaderSize = 5

// Scroll message size
// type(1) + x(4) + y(4) + width(4) + height(4) + dx(4) + dy(4) = 25 bytes
const ScrollMessageSize = 25
