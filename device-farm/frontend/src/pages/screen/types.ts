export interface UIElementBounds {
  x: number
  y: number
  width: number
  height: number
}

export interface UISelectorSuggestion {
  type: string
  value: string
}

export interface UIElementNode {
  uid: string
  parent_uid?: string | null
  depth: number
  index: number
  class_name: string
  resource_id: string
  text: string
  content_desc: string
  package: string
  bounds: UIElementBounds
  center: { x: number; y: number }
  clickable: boolean
  enabled: boolean
  selected: boolean
  focused: boolean
  scrollable: boolean
  xpath: string
  selector_suggestions: UISelectorSuggestion[]
  attributes?: Record<string, unknown>
}

export interface UIHierarchyResponse {
  device_id: string
  platform: string
  captured_at: string
  screen: { width: number; height: number }
  elements: UIElementNode[]
}

export interface RenderMetrics {
  left: number
  top: number
  width: number
  height: number
}

export interface StaticDebugActionResponse {
  success?: boolean
  screen?: { width: number; height: number } | null
  latency_ms?: number
  control_method?: string
  session_reused?: boolean
}

export interface IOSMJPEGPrepareResponse {
  screen?: { width: number; height: number } | null
}

export interface StaticDebugPoint {
  x: number
  y: number
}

export interface ScreenSessionDiagnostics {
  active?: boolean
  stage?: string
  stage_label?: string
  durations_ms?: Record<string, number>
  frame_count?: number
  key_frame_count?: number
  last_error?: string
  reused?: boolean
}

export interface LocatorSnippet {
  key: string
  title: string
  description: string
  code: string
}

export type WorkspaceTab = 'inspect' | 'script' | 'logcat'
