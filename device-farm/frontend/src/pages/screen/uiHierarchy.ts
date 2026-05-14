import type { LocatorSnippet, UIElementNode } from './types'

export function pythonString(value: string) {
  return JSON.stringify(value)
}

export function findSelector(element: UIElementNode, type: string) {
  return element.selector_suggestions.find((selector) => selector.type === type)?.value || ''
}

function isFalseAttribute(value: unknown) {
  return value === false || value === 'false' || value === 0 || value === '0'
}

function hasUsefulOverlaySignal(element: UIElementNode, isIos: boolean) {
  return Boolean(
    (!isIos && element.clickable)
    || element.scrollable
    || element.focused
    || element.selected
    || element.resource_id
    || element.text
    || element.content_desc,
  )
}

export function overlayBounds(element: UIElementNode, screen: { width: number; height: number }) {
  const left = Math.max(0, element.bounds.x)
  const top = Math.max(0, element.bounds.y)
  const right = Math.min(screen.width, element.bounds.x + element.bounds.width)
  const bottom = Math.min(screen.height, element.bounds.y + element.bounds.height)
  const width = Math.max(0, right - left)
  const height = Math.max(0, bottom - top)
  return { left, top, width, height }
}

function shouldRenderElementBox(element: UIElementNode, screen: { width: number; height: number }, isIos: boolean) {
  if (element.bounds.width <= 0 || element.bounds.height <= 0 || screen.width <= 0 || screen.height <= 0) {
    return false
  }

  const clipped = overlayBounds(element, screen)
  if (clipped.width <= 0 || clipped.height <= 0) {
    return false
  }

  if (!isIos) {
    return true
  }

  if (isFalseAttribute(element.attributes?.visible)) {
    return false
  }

  const screenArea = screen.width * screen.height
  const areaRatio = (clipped.width * clipped.height) / screenArea
  if (areaRatio > 0.85) {
    return false
  }

  return hasUsefulOverlaySignal(element, true) || areaRatio < 0.5
}

function iOSOverlayElementScore(element: UIElementNode) {
  let score = 0
  if (element.text) score += 100
  if (element.content_desc) score += 80
  if (element.focused || element.selected) score += 40
  if (element.scrollable) score += 20
  if (element.class_name.includes('Button') || element.class_name.includes('Cell') || element.class_name.includes('TextField')) {
    score += 35
  } else if (element.class_name.includes('StaticText')) {
    score += 25
  } else if (element.class_name.includes('Image')) {
    score -= 10
  }
  score += element.depth
  return score
}

function dedupeIOSOverlayElements(elements: UIElementNode[]) {
  const byBounds = new Map<string, UIElementNode>()
  for (const element of elements) {
    const key = `${element.bounds.x}:${element.bounds.y}:${element.bounds.width}:${element.bounds.height}`
    const existing = byBounds.get(key)
    if (!existing || iOSOverlayElementScore(element) > iOSOverlayElementScore(existing)) {
      byBounds.set(key, element)
    }
  }
  return Array.from(byBounds.values())
}

export function buildVisibleUiElements(
  uiElements: UIElementNode[],
  uiScreen: { width: number; height: number } | null,
  isIosDevice: boolean,
) {
  if (!uiScreen) return []
  const elementsForOverlay = uiElements
    .filter((element) => shouldRenderElementBox(element, uiScreen, isIosDevice))
  const dedupedElements = isIosDevice ? dedupeIOSOverlayElements(elementsForOverlay) : elementsForOverlay
  return dedupedElements
    .map((element) => {
      const bounds = overlayBounds(element, uiScreen)
      const areaRatio = (bounds.width * bounds.height) / (uiScreen.width * uiScreen.height)
      return {
        element,
        bounds,
        zIndex: Math.max(1, Math.round((1 - areaRatio) * 1000) + element.depth),
      }
    })
    .sort((a, b) => {
      const areaA = a.bounds.width * a.bounds.height
      const areaB = b.bounds.width * b.bounds.height
      return areaB - areaA
    })
}

export function buildLocatorSnippets(element: UIElementNode | null, platform = 'android'): LocatorSnippet[] {
  if (!element) return []

  const snippets: LocatorSnippet[] = []
  if (platform === 'ios') {
    const accessibilityId = findSelector(element, 'accessibility_id') || element.content_desc
    const predicate = findSelector(element, 'ios_predicate')
    const classChain = findSelector(element, 'ios_class_chain')

    if (accessibilityId) {
      snippets.push({
        key: 'ios-click-accessibility',
        title: '按 accessibility-id 点击',
        description: '推荐用于 iOS 上稳定的 name 或 accessibility label。',
        code: `app.click(AppiumBy.ACCESSIBILITY_ID, ${pythonString(accessibilityId)}, timeout=10)`,
      })
    }
    if (predicate) {
      snippets.push({
        key: 'ios-click-predicate',
        title: '按 iOS Predicate 点击',
        description: '适合用 name、label 或 value 精确定位。',
        code: `app.click(AppiumBy.IOS_PREDICATE, ${pythonString(predicate)}, timeout=10)`,
      })
    }
    if (classChain) {
      snippets.push({
        key: 'ios-click-class-chain',
        title: '按 iOS Class Chain 点击',
        description: '适合没有稳定 accessibility id 时缩小控件类型范围。',
        code: `app.click(AppiumBy.IOS_CLASS_CHAIN, ${pythonString(classChain)}, timeout=10)`,
      })
    }
    if (element.text) {
      snippets.push({
        key: 'ios-assert-text',
        title: '断言文本存在',
        description: 'iOS 会按 label、name、value 查询文本。',
        code: `app.assert_text(${pythonString(element.text)})`,
      })
    }
    if (element.xpath) {
      snippets.push({
        key: 'ios-click-xpath',
        title: '按 XPath 点击',
        description: '结构变化时需要维护，建议作为兜底。',
        code: `app.click(AppiumBy.XPATH, ${pythonString(element.xpath)}, timeout=10)`,
      })
    }
    snippets.push({
      key: 'ios-tap-coordinate',
      title: '按坐标点击',
      description: '兜底方案，分辨率或布局变化时稳定性较弱。',
      code: `app.tap(${Math.round(element.center.x)}, ${Math.round(element.center.y)})`,
    })
    return snippets
  }

  if (element.resource_id) {
    snippets.push({
      key: 'click-id',
      title: '按 resource-id 点击',
      description: '推荐用于稳定控件，优先级最高。',
      code: `app.click(AppiumBy.ID, ${pythonString(element.resource_id)}, timeout=10)`,
    })
    snippets.push({
      key: 'get-text-id',
      title: '按 resource-id 读取文本',
      description: '适合断言标题、按钮文案或输入框内容。',
      code: `text = app.get_text(AppiumBy.ID, ${pythonString(element.resource_id)}, timeout=10)\napp.log(f"element text: {text}")`,
    })
  }

  if (element.content_desc) {
    snippets.push({
      key: 'click-accessibility',
      title: '按 accessibility-id 点击',
      description: '适合有 content-desc 的图标按钮。',
      code: `app.click(AppiumBy.ACCESSIBILITY_ID, ${pythonString(element.content_desc)}, timeout=10)`,
    })
  }

  if (element.text) {
    if (element.clickable) {
      snippets.push({
        key: 'click-text',
        title: '按文本点击',
        description: '适合弹窗按钮、菜单项等短文本控件。',
        code: `app.click_text(${pythonString(element.text)}, timeout=5)`,
      })
    }
    snippets.push({
      key: 'assert-text',
      title: '断言文本存在',
      description: element.clickable ? '适合验证页面是否进入预期状态。' : '当前控件不可点击，建议用于断言；点击请优先选择可点击父级控件。',
      code: `app.assert_text(${pythonString(element.text)})`,
    })
  }

  if (element.xpath) {
    snippets.push({
      key: 'click-xpath',
      title: '按 XPath 点击',
      description: '当没有稳定 ID 时使用，页面结构变化时需要维护。',
      code: `app.click(AppiumBy.XPATH, ${pythonString(element.xpath)}, timeout=10)`,
    })
  }

  snippets.push({
    key: 'tap-coordinate',
    title: '按坐标点击',
    description: '兜底方案，分辨率或布局变化时稳定性较弱。',
    code: `app.tap(${Math.round(element.center.x)}, ${Math.round(element.center.y)})`,
  })

  return snippets
}
