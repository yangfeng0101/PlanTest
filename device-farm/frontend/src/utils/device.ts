import type { Device, DeviceCapabilities, DeviceDrivers } from '@/types'

type RawRecord = Record<string, unknown>

const defaultDrivers: DeviceDrivers = {
  metrics: '',
  screen: '',
  uiHierarchy: '',
  control: '',
  automation: '',
}

const defaultCapabilities: DeviceCapabilities = {
  screenMirror: false,
  remoteControl: false,
  uiHierarchy: false,
  metrics: false,
  screenshot: false,
  appManagement: false,
  automation: false,
}

export const formatOsName = (os: string) => {
  const normalized = os.toLowerCase()
  if (normalized === 'harmony') return 'HarmonyOS'
  if (normalized === 'android') return 'Android'
  if (normalized === 'ios') return 'iOS'
  return os || 'Unknown'
}

export const mapDevice = (d: RawRecord): Device => {
  const rawDrivers = (d.drivers || {}) as RawRecord
  const rawCapabilities = (d.capabilities || {}) as RawRecord
  const os = (d.os as string) || 'android'
  const osVersion = (d.os_version as string) || ''
  const androidCompatible = ['android', 'harmony'].includes(os.toLowerCase())
  const inferredCapabilities: DeviceCapabilities = {
    screenMirror: androidCompatible,
    remoteControl: androidCompatible,
    uiHierarchy: androidCompatible,
    metrics: androidCompatible || os.toLowerCase() === 'ios',
    screenshot: androidCompatible,
    appManagement: androidCompatible,
    automation: androidCompatible,
  }

  return {
    id: d.id as string,
    name: d.name as string,
    model: d.model as string,
    brand: d.brand as string,
    os,
    osVersion,
    displayOs: (d.display_os as string) || formatOsName(os),
    displayOsVersion: (d.display_os_version as string) || osVersion,
    connectionType: (d.connection_type as string) || '',
    drivers: {
      metrics: (rawDrivers.metrics as string) || defaultDrivers.metrics,
      screen: (rawDrivers.screen as string) || defaultDrivers.screen,
      uiHierarchy: (rawDrivers.ui_hierarchy as string) || defaultDrivers.uiHierarchy,
      control: (rawDrivers.control as string) || defaultDrivers.control,
      automation: (rawDrivers.automation as string) || defaultDrivers.automation,
    },
    capabilities: {
      screenMirror: Boolean(rawCapabilities.screen_mirror ?? inferredCapabilities.screenMirror ?? defaultCapabilities.screenMirror),
      remoteControl: Boolean(rawCapabilities.remote_control ?? inferredCapabilities.remoteControl ?? defaultCapabilities.remoteControl),
      uiHierarchy: Boolean(rawCapabilities.ui_hierarchy ?? inferredCapabilities.uiHierarchy ?? defaultCapabilities.uiHierarchy),
      metrics: Boolean(rawCapabilities.metrics ?? inferredCapabilities.metrics ?? defaultCapabilities.metrics),
      screenshot: Boolean(rawCapabilities.screenshot ?? inferredCapabilities.screenshot ?? defaultCapabilities.screenshot),
      appManagement: Boolean(rawCapabilities.app_management ?? inferredCapabilities.appManagement ?? defaultCapabilities.appManagement),
      automation: Boolean(rawCapabilities.automation ?? inferredCapabilities.automation ?? defaultCapabilities.automation),
    },
    status: d.status as Device['status'],
    screenResolution: (d.screen_resolution as string) || '',
    screenSize: (d.screen_size as number) || 5.5,
    cpu: (d.cpu as string) || '',
    memory: (d.memory as string) || '',
    storage: (d.storage as string) || '',
    batteryLevel: (d.battery_level as number) || 100,
    occupiedBy: d.occupied_by as string | undefined,
    occupiedAt: d.occupied_at as string | undefined,
    lastActiveAt: (d.last_active_at as string) || '',
    tags: (d.tags as string[]) || [],
    thumbnail: d.thumbnail as string | undefined,
  }
}

export const formatDeviceOs = (device: Device) => {
  const name = device.displayOs || formatOsName(device.os)
  const version = device.displayOsVersion || device.osVersion
  return `${name} ${version}`.trim()
}
