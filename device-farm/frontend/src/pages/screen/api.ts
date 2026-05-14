import type {
  IOSMJPEGPrepareResponse,
  ScreenSessionDiagnostics,
  StaticDebugActionResponse,
  UIHierarchyResponse,
} from './types'

export const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || ''
export const TOUCH_MOVE_INTERVAL_MS = 16
export const STATIC_AUTO_REFRESH_INTERVAL_OPTIONS = [
  { label: '1s', value: 1000 },
  { label: '2s', value: 2000 },
  { label: '5s', value: 5000 },
]
export const IOS_DIRECT_MJPEG_SCREEN_DRIVERS = new Set([
  'mjpeg-direct',
  'wda-mjpeg',
  'wda-mjpeg-direct',
  'ios-mjpeg',
  'ios-mjpeg-direct',
])
export const KEYBOARD_KEY_CODE_MAP: Record<string, number> = {
  Backspace: 67,
  Enter: 66,
  Tab: 61,
  Escape: 111,
  Delete: 112,
  ArrowUp: 19,
  ArrowDown: 20,
  ArrowLeft: 21,
  ArrowRight: 22,
}

async function readJson<T>(response: Response): Promise<T> {
  return response.json().catch(() => ({})) as Promise<T>
}

export function requestStopSession(deviceId: string) {
  void fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/stop`, {
    method: 'POST',
    credentials: 'include',
    keepalive: true,
  }).catch((error) => {
    console.error('Failed to stop session:', error)
  })
}

export function requestStopIOSMJPEG(deviceId: string) {
  void fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/ios-mjpeg`, {
    method: 'DELETE',
    credentials: 'include',
    keepalive: true,
  }).catch((error) => {
    console.error('Failed to stop iOS MJPEG stream:', error)
  })
}

export async function releaseDebugSession(deviceId: string, keepalive = false) {
  const res = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/debug-session`, {
    method: 'DELETE',
    credentials: 'include',
    keepalive,
  })
  return res.ok
}

export function requestReleaseDebugSession(deviceId: string) {
  void releaseDebugSession(deviceId, true).catch((error) => {
    console.error('Failed to release debug session:', error)
  })
}

export async function fetchDevicesPayload() {
  const res = await fetch('/api/v1/devices')
  return readJson<{ devices?: Record<string, unknown>[] }>(res)
}

export async function fetchDeviceScreenInfo(deviceId: string) {
  const res = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`)
  return readJson<{ screen_resolution?: string; screenResolution?: string }>(res)
}

export async function prepareIOSMJPEGSession(deviceId: string) {
  const res = await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/ios-mjpeg/prepare`, {
    method: 'POST',
    credentials: 'include',
  })
  const data = await readJson<IOSMJPEGPrepareResponse & { error?: string }>(res)
  if (!res.ok) {
    throw new Error(data.error || 'iOS MJPEG 直连预览初始化失败')
  }
  return data
}

export async function startLiveKitSession(deviceId: string) {
  const res = await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  })
  const data = await readJson<ScreenSessionDiagnostics & {
    error?: string
    livekit_url?: string
    token?: string
    video_width?: number
    videoWidth?: number
    video_height?: number
    videoHeight?: number
  }>(res)
  if (!res.ok || !data.token) {
    throw new Error(data.error || '无法获取连接 Token')
  }
  return data as typeof data & { token: string }
}

export async function fetchDeviceScreenshot(deviceId: string, signal?: AbortSignal) {
  const res = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/screenshot`, {
    credentials: 'include',
    signal,
  })
  const data = await readJson<Record<string, unknown> & { detail?: string }>(res)
  if (!res.ok) {
    throw new Error(data.detail || '刷新截图失败')
  }
  if (!data.image) {
    throw new Error('截图数据为空')
  }
  return data
}

export async function fetchUIHierarchy(
  deviceId: string,
  isIosDirectMjpegMirror: boolean,
  signal?: AbortSignal,
) {
  const endpoint = isIosDirectMjpegMirror
    ? `${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/ios-mjpeg/ui-hierarchy`
    : `/api/v1/devices/${encodeURIComponent(deviceId)}/ui-hierarchy`
  const res = await fetch(endpoint, {
    credentials: 'include',
    signal,
  })
  const data = await readJson<UIHierarchyResponse & { detail?: string }>(res)
  if (!res.ok) {
    throw new Error(data.detail || '获取控件失败')
  }
  return data
}

export async function postIOSDebugAction(
  deviceId: string,
  path: 'tap' | 'text' | 'swipe' | 'long-press' | 'clear-text',
  payload: Record<string, unknown>,
  options: { isIosDirectMjpegMirror: boolean; includeScreen: boolean },
) {
  const endpoint = options.isIosDirectMjpegMirror
    ? `${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/ios-mjpeg/debug/${path}`
    : `/api/v1/devices/${encodeURIComponent(deviceId)}/debug/${path}`
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ includeScreen: options.includeScreen, ...payload }),
  })
  const data = await readJson<StaticDebugActionResponse & { detail?: string; error?: string }>(res)
  if (!res.ok) {
    throw new Error(data.detail || data.error || 'iOS 静态操作失败')
  }
  return data
}

export async function fetchSessionDiagnostics(deviceId: string) {
  const res = await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}`, {
    credentials: 'include',
  })
  const data = await readJson<ScreenSessionDiagnostics>(res)
  if (!res.ok) {
    throw new Error('获取投屏诊断失败')
  }
  return data
}

export function buildIOSMJPEGStreamUrl(deviceId: string, key: number) {
  const query = new URLSearchParams({ t: String(key) })
  return `${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/ios-mjpeg?${query.toString()}`
}
