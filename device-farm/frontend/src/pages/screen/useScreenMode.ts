import type { Device } from '@/types'
import { IOS_DIRECT_MJPEG_SCREEN_DRIVERS } from './api'

export default function useScreenMode(currentDevice: Device | undefined) {
  const screenMirrorSupported = currentDevice?.capabilities.screenMirror ?? false
  const remoteControlSupported = currentDevice?.capabilities.remoteControl ?? false
  const uiHierarchySupported = currentDevice?.capabilities.uiHierarchy ?? false
  const screenshotSupported = currentDevice?.capabilities.screenshot ?? false
  const isIosDevice = Boolean(currentDevice && currentDevice.os.toLowerCase() === 'ios')
  const screenDriver = (currentDevice?.drivers.screen || '').trim().toLowerCase()
  const isIosDirectMjpegMirror = Boolean(
    isIosDevice
    && screenMirrorSupported
    && IOS_DIRECT_MJPEG_SCREEN_DRIVERS.has(screenDriver)
  )
  const isIosLivePreview = isIosDirectMjpegMirror
  const isIosStaticDebug = Boolean(
    isIosDevice
    && !screenMirrorSupported
    && uiHierarchySupported
    && screenshotSupported
  )
  const isIosStaticActionSupported = Boolean(isIosDevice && uiHierarchySupported && screenshotSupported)
  const iosModeLabel = isIosDirectMjpegMirror
    ? 'iOS MJPEG 直连预览'
    : 'iOS 静态预览'

  return {
    screenMirrorSupported,
    remoteControlSupported,
    uiHierarchySupported,
    screenshotSupported,
    isIosDevice,
    isIosDirectMjpegMirror,
    isIosLivePreview,
    isIosStaticDebug,
    isIosStaticActionSupported,
    iosModeLabel,
  }
}
