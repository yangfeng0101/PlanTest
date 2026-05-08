# 自动化脚本使用指南

本文档说明平台 Python 自动化脚本当前支持的方法，以及推荐的脚本编写方式。

当前脚本 SDK 版本：`1.3.0`。版本信息主要用于平台维护和问题排查，普通脚本编写优先关注下方列出的可操作方法。

## 平台支持

- Android/HarmonyOS：支持脚本执行、投屏页调试、控件树辅助和 Midscene AI 兜底。
- iOS v1：支持通过 Mac 宿主机 iOS Agent + Appium XCUITest 执行 Python 脚本；不支持投屏页调试、控件树辅助和 Midscene AI。
- iOS 脚本内 `app.screenshot()` 走 Appium 截图并上传到任务详情，不代表设备详情页截图能力可用。
- iOS 设备只有在 Agent 返回 `automation_ready=true` 时才会出现在脚本运行设备列表中；默认需要先完成 WDA 真机验证，并把已验证 UDID 加入 `IOS_AGENT_AUTOMATION_READY_UDIDS`。
- 真机 WDA 签名可通过 `IOS_XCODE_ORG_ID`、`IOS_XCODE_SIGNING_ID`、`IOS_WDA_BUNDLE_ID` 和 `IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION` 配置传入 `test-svc` / `test-worker`。
- iOS 本机环境配置见 `docs/deployment/IOS_AGENT_SETUP.md`；可先用 `scripts/examples/ios_settings_smoke.py` 做设置页 smoke。

## 推荐原则

优先使用 `app.xxx` 形式调用平台能力，例如：

```python
app.log("start")
app.activate_app("com.shizhuang.duapp")
app.screenshot()
app.terminate_app("com.shizhuang.duapp")
test_pass()
```

不推荐在新脚本里继续使用旧的全局函数，例如 `log()`、`tap()`、`screenshot()`。这些函数仍然保留用于兼容历史脚本。

创建任务时只需要选择设备。启动哪个 App、什么时候启动、什么时候退出，都建议写在脚本内容里。

## 完整 API 速查

### 推荐使用的 `app` 方法

| 分类 | 方法 | 作用 |
| --- | --- | --- |
| App 控制 | `app.activate_app(package_name)` | 启动或拉起指定 App |
| App 控制 | `app.launch_app(package_name)` | 启动或拉起指定 App |
| App 控制 | `app.launch_app()` | 拉起当前 session 绑定的 App |
| App 控制 | `app.terminate_app(package_name)` | 退出或杀掉指定 App |
| App 控制 | `app.close_app(package_name)` | 退出或杀掉指定 App |
| App 控制 | `app.close_app()` | 关闭当前 session 绑定的 App |
| App 控制 | `app.restart_app(package_name, wait_seconds=1)` | 退出后等待并重新启动指定 App |
| App 控制 | `app.back()` | 返回键 |
| App 控制 | `app.home()` | Home 键 |
| 日志与等待 | `app.log(message, level="INFO")` | 写入执行日志 |
| 日志与等待 | `app.wait(seconds=1)` | 固定等待 |
| 截图与源码 | `app.screenshot()` | 截图并上传到任务详情 |
| 截图与源码 | `app.source()` | 获取当前页面源码/控件树 |
| 底层能力 | `app.driver` | 获取底层 Appium driver |
| 手势 | `app.tap(x, y)` | 点击坐标 |
| 手势 | `app.swipe(start_x, start_y, end_x, end_y, duration=500)` | 滑动 |
| 输入 | `app.input_text(text)` | 向当前焦点输入文本 |
| 输入 | `app.clear_text(by=None, value=None, timeout=0)` | 清空当前焦点或指定元素文本 |
| 输入 | `app.press_key(keycode)` | 发送 Android keycode |
| 文本 | `app.has_text(text)` | 判断页面是否包含文本 |
| 文本 | `app.assert_text(text)` | 断言页面包含文本 |
| 文本 | `app.wait_text(text, timeout=10)` | 等待文本出现 |
| 元素 | `app.find(by, value, timeout=0)` | 查找单个元素 |
| 元素 | `app.find_all(by, value)` | 查找多个元素 |
| 元素 | `app.wait_element(by, value, timeout=10)` | 等待元素出现 |
| 元素 | `app.exists(by, value, timeout=0)` | 判断元素是否存在 |
| 元素 | `app.click(by, value, timeout=0)` | 查找并点击元素 |
| 元素 | `app.get_text(by, value, timeout=0)` | 查找元素并返回文本 |
| 元素 | `app.click_text(text, timeout=5)` | Android 按 `text/content-desc` 点击；iOS 按 `label/name/value` 点击 |
| 元素 | `app.tap_text(text, timeout=5)` | 等价于 `app.click_text()` |
| AI 操作 | `app.ai(instruction, timeout=30)` | 使用自然语言完成一组操作 |
| AI 操作 | `app.ai_act(instruction, timeout=30)` | 等价于 `app.ai()` 的显式动作版本 |
| AI 定位 | `app.ai_locate(target, timeout=10, deep_locate=False)` | 返回 Midscene 定位结果 |
| AI 操作 | `app.ai_tap(target, timeout=10, deep_locate=False)` | 自然语言定位并点击 |
| AI 输入 | `app.ai_input(target, text, clear=True, timeout=10, deep_locate=False)` | 定位输入框并输入文本 |
| AI 输入 | `app.ai_clear(target, timeout=10, deep_locate=False)` | 定位并清空输入框 |
| AI 输入 | `app.ai_key(key, target=None, timeout=10, deep_locate=False)` | 发送键盘按键 |
| AI 手势 | `app.ai_scroll(target=None, direction="down", distance=None, scroll_type="singleAction", timeout=15, deep_locate=False)` | 自然语言定位区域并滚动 |
| AI 手势 | `app.ai_long_press(target, duration=None, timeout=10, deep_locate=False)` | 长按目标 |
| AI 手势 | `app.ai_double_tap(target, timeout=10, deep_locate=False)` | 双击目标 |
| AI 断言 | `app.ai_wait(assertion, timeout=15, check_interval=3)` | 等待自然语言断言成立 |
| AI 断言 | `app.ai_assert(assertion, error_message=None, timeout=10)` | 校验自然语言断言 |

### 全局函数和对象

| 名称 | 作用 | 推荐程度 |
| --- | --- | --- |
| `test_pass()` | 标记一个测试通过 | 推荐 |
| `test_fail(msg="")` | 标记一个测试失败 | 推荐 |
| `test_skip()` | 标记一个测试跳过 | 推荐 |
| `assert_true(value, message="Assertion failed")` | 断言表达式为真 | 推荐 |
| `assert_equal(actual, expected, message=None)` | 断言两个值相等 | 推荐 |
| `driver` | 底层 Appium driver | 高阶场景使用 |
| `params` | 任务参数 | 按需使用 |
| `task_id` | 当前任务 ID | 按需使用 |
| `AppiumBy` | Appium 定位方式枚举 | 推荐 |
| `datetime` / `date` / `timedelta` | 时间处理 | 推荐 |
| `Decimal` | 高精度数字 | 按需使用 |

## App 控制

| 方法 | 作用 | 推荐 |
| --- | --- | --- |
| `app.activate_app(package_name)` | 启动或拉起指定 App | 是 |
| `app.launch_app(package_name)` | 启动或拉起指定 App，带包名时等价于 `activate_app` | 是 |
| `app.launch_app()` | 拉起当前 Appium session 绑定的 App | 一般 |
| `app.terminate_app(package_name)` | 退出或杀掉指定 App | 是 |
| `app.close_app(package_name)` | 带包名时等价于 `terminate_app` | 一般 |
| `app.close_app()` | 关闭当前 App | 一般 |
| `app.restart_app(package_name, wait_seconds=1)` | 先退出指定 App，再等待并重新启动 | 是 |
| `app.back()` | 返回上一页 | 是 |
| `app.home()` | 回到系统桌面 | 是 |

示例：

```python
package = "com.shizhuang.duapp"

app.activate_app(package)
app.wait(5)
app.screenshot()
app.terminate_app(package)
```

## 基础能力

| 方法 | 参数 | 作用 | 返回值 |
| --- | --- | --- | --- |
| `app.log(message, level="INFO")` | `message`: 日志内容；`level`: `INFO/WARN/ERROR/DEBUG` | 写入任务日志 | 无 |
| `app.wait(seconds=1)` | `seconds`: 秒数，支持小数 | 等待指定秒数 | 无 |
| `app.screenshot()` | 无 | 截图并上传到任务详情 | 截图 URL |
| `app.source()` | 无 | 获取当前页面源码/控件树 | 字符串 |
| `app.driver` | 无 | 获取底层 Appium driver | driver 对象 |

日志级别建议使用：

```python
app.log("普通日志")
app.log("警告信息", "WARN")
app.log("错误信息", "ERROR")
```

## 手势和输入

| 方法 | 参数 | 作用 | 示例 |
| --- | --- | --- | --- |
| `app.tap(x, y)` | `x/y`: 屏幕坐标 | 点击屏幕坐标 | `app.tap(500, 1200)` |
| `app.swipe(start_x, start_y, end_x, end_y, duration=500)` | 起点、终点、持续时间毫秒 | 滑动 | `app.swipe(500, 1600, 500, 400)` |
| `app.input_text(text)` | `text`: 输入内容 | 向当前焦点输入文本 | `app.input_text("hello")` |
| `app.clear_text(by=None, value=None, timeout=0)` | 可选定位参数 | 清空当前焦点或指定元素文本 | `app.clear_text()` |
| `app.press_key(keycode)` | `keycode`: Android 按键码 | Android 按键 | `app.press_key(4)` |

常用 Android keycode：

| Keycode | 作用 |
| --- | --- |
| `4` | 返回键 |
| `3` | Home 键 |
| `24` | 音量加 |
| `25` | 音量减 |
| `66` | Enter 键 |
| `67` | 删除键 |
| `82` | 菜单键 |
| `187` | 最近任务 |

## 文本判断

| 方法 | 参数 | 作用 | 返回/失败行为 |
| --- | --- | --- | --- |
| `app.has_text(text)` | `text`: 文本 | 判断页面源码里是否包含文本 | 返回 `True/False` |
| `app.assert_text(text)` | `text`: 文本 | 断言页面存在文本 | 不存在则任务失败 |
| `app.wait_text(text, timeout=10)` | `text`: 文本；`timeout`: 秒数 | 等待文本出现 | 出现返回 `True`，超时则任务失败 |

示例：

```python
if app.has_text("同意"):
    app.click_text("同意", timeout=5)

app.wait_text("首页", timeout=15)
```

## 元素定位

平台支持 XPath、ID、Accessibility ID、Class Name、Android UIAutomator 等定位方式。

| 方法 | 参数 | 作用 | 返回值 |
| --- | --- | --- | --- |
| `app.find(by, value, timeout=0)` | `by`: 定位方式；`value`: 定位表达式；`timeout`: 秒数 | 查找单个元素 | 元素对象 |
| `app.find_all(by, value)` | `by`: 定位方式；`value`: 定位表达式 | 查找多个元素 | 元素对象列表 |
| `app.wait_element(by, value, timeout=10)` | `by`: 定位方式；`value`: 定位表达式；`timeout`: 秒数 | 等待元素出现 | 元素对象 |
| `app.exists(by, value, timeout=0)` | `by`: 定位方式；`value`: 定位表达式；`timeout`: 秒数 | 判断元素是否存在 | `True/False` |
| `app.click(by, value, timeout=0)` | `by`: 定位方式；`value`: 定位表达式；`timeout`: 秒数 | 查找并点击元素 | 被点击的元素对象 |
| `app.get_text(by, value, timeout=0)` | `by`: 定位方式；`value`: 定位表达式；`timeout`: 秒数 | 获取元素文本 | 字符串 |
| `app.click_text(text, timeout=5)` | `text`: 文本；`timeout`: 秒数 | Android 按 `text/content-desc`；iOS 按 `label/name/value` 点击 | 被点击的元素对象 |
| `app.tap_text(text, timeout=5)` | `text`: 文本；`timeout`: 秒数 | 等价于 `click_text` | 被点击的元素对象 |

常用 `AppiumBy`：

| 定位方式 | 用法 | 说明 |
| --- | --- | --- |
| XPath | `AppiumBy.XPATH` | 灵活但相对慢，适合兜底 |
| ID | `AppiumBy.ID` | 推荐，通常对应 Android `resource-id` |
| Accessibility ID | `AppiumBy.ACCESSIBILITY_ID` | 推荐，通常对应 Android `content-desc` |
| Class Name | `AppiumBy.CLASS_NAME` | 适合查找同类控件 |
| Android UIAutomator | `AppiumBy.ANDROID_UIAUTOMATOR` | Android 专用，能力强 |
| iOS Predicate | `AppiumBy.IOS_PREDICATE` | iOS 专用 |
| iOS Class Chain | `AppiumBy.IOS_CLASS_CHAIN` | iOS 专用 |

### XPath

```python
app.click(AppiumBy.XPATH, '//*[@text="登录"]', timeout=10)
app.click(AppiumBy.XPATH, '//*[@content-desc="搜索"]', timeout=10)
app.click(AppiumBy.XPATH, '//*[contains(@text, "登录")]', timeout=10)
```

### ID

```python
app.click(AppiumBy.ID, "com.shizhuang.duapp:id/login_button", timeout=10)

element = app.find(AppiumBy.ID, "com.shizhuang.duapp:id/search_input", timeout=10)
element.click()
element.send_keys("鞋子")
```

### Accessibility ID / content-desc

```python
app.click(AppiumBy.ACCESSIBILITY_ID, "搜索", timeout=10)
```

### Class Name

```python
items = app.find_all(AppiumBy.CLASS_NAME, "android.widget.TextView")
app.log(f"TextView count: {len(items)}")

if len(items) > 0:
    app.log(items[0].text)
```

### Android UIAutomator

```python
app.click(
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().text("登录")',
    timeout=10,
)
```

更多 Android UIAutomator 示例：

```python
app.click(
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().resourceId("com.shizhuang.duapp:id/search")',
    timeout=10,
)

app.click(
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().textContains("登录")',
    timeout=10,
)

app.click(
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().descriptionContains("搜索")',
    timeout=10,
)
```

## 元素对象常用能力

`app.find()`、`app.click()`、`app.click_text()` 返回的是 Appium 元素对象。常用能力如下：

| 方法/属性 | 作用 | 示例 |
| --- | --- | --- |
| `element.click()` | 点击元素 | `element.click()` |
| `element.send_keys(text)` | 输入文本 | `element.send_keys("hello")` |
| `element.clear()` | 清空输入框 | `element.clear()` |
| `element.text` | 获取元素文本 | `app.log(element.text)` |
| `element.get_attribute(name)` | 获取元素属性 | `element.get_attribute("enabled")` |
| `element.is_displayed()` | 判断是否显示 | `assert_true(element.is_displayed())` |
| `element.is_enabled()` | 判断是否可用 | `assert_true(element.is_enabled())` |
| `element.location` | 获取元素坐标 | `app.log(str(element.location))` |
| `element.size` | 获取元素尺寸 | `app.log(str(element.size))` |

示例：

```python
input_box = app.find(AppiumBy.ID, "com.example:id/input", timeout=10)
input_box.clear()
input_box.send_keys("hello")

button = app.find(AppiumBy.XPATH, '//*[@text="确定"]', timeout=10)
assert_true(button.is_enabled(), "确定按钮不可用")
button.click()
```

## AI 操作

AI 操作由后端 `midscene-runner` 调用 Midscene Android 能力完成，适合控件树不稳定、页面动画导致 UIAutomator 难以稳定定位，或临时需要用自然语言兜底的场景。它需要管理员在容器环境中配置 Midscene 模型环境变量；脚本中不要写模型密钥。

> iOS v1 暂不支持 `app.ai_xxx()`。iOS 请优先使用 `AppiumBy.ACCESSIBILITY_ID`、`AppiumBy.IOS_PREDICATE`、`AppiumBy.IOS_CLASS_CHAIN` 或 XPath。

| 方法 | 作用 | 返回/失败行为 |
| --- | --- | --- |
| `app.ai(instruction, timeout=30)` | 按自然语言描述完成一组操作 | 返回 Midscene 执行结果；失败则任务失败 |
| `app.ai_act(instruction, timeout=30)` | 与 `app.ai()` 等价，显式表示执行动作 | 返回 Midscene 执行结果；失败则任务失败 |
| `app.ai_locate(target, timeout=10, deep_locate=False)` | 自然语言定位目标 | 返回 `rect`、`center` 等定位信息 |
| `app.ai_tap(target, timeout=10, deep_locate=False)` | 定位并点击目标 | 失败则任务失败 |
| `app.ai_input(target, text, clear=True, timeout=10, deep_locate=False)` | 定位输入框并输入文本 | `clear=True` 会替换原文本；`False` 仅追加输入 |
| `app.ai_clear(target, timeout=10, deep_locate=False)` | 定位并清空输入框 | 失败则任务失败 |
| `app.ai_key(key, target=None, timeout=10, deep_locate=False)` | 发送键盘按键，可先定位目标 | 失败则任务失败 |
| `app.ai_scroll(target=None, direction="down", distance=None, scroll_type="singleAction", timeout=15, deep_locate=False)` | 在目标区域或当前页面滚动 | 失败则任务失败 |
| `app.ai_long_press(target, duration=None, timeout=10, deep_locate=False)` | 长按目标 | 失败则任务失败 |
| `app.ai_double_tap(target, timeout=10, deep_locate=False)` | 双击目标 | 失败则任务失败 |
| `app.ai_wait(assertion, timeout=15, check_interval=3)` | 等待自然语言断言成立 | 成功返回 `True`，超时则任务失败 |
| `app.ai_assert(assertion, error_message=None, timeout=10)` | 校验自然语言断言 | 失败抛 `AssertionError` |

示例：

```python
app.activate_app("com.example.app")
app.wait(2)

search_box = app.ai_locate("搜索框")
app.log(f"搜索框中心点: {search_box.get('center')}")

app.ai_tap("搜索框")
app.ai_input("搜索框", "跑鞋")
app.ai_key("Enter")
app.ai_wait("页面展示搜索结果", timeout=20)
app.ai_scroll("商品列表", direction="down")
app.ai_assert("页面仍然展示商品列表", "搜索结果列表未展示")
```

`deep_locate=True` 会让 Midscene 使用更深度的定位策略，通常更慢，建议只在普通定位不稳定时使用。

## 测试结果和断言

| 方法 | 参数 | 作用 | 失败行为 |
| --- | --- | --- | --- |
| `test_pass()` | 无 | 标记一个测试通过 | 不失败 |
| `test_fail(msg="")` | `msg`: 失败原因 | 标记一个测试失败 | 任务结果失败 |
| `test_skip()` | 无 | 标记一个测试跳过 | 不失败 |
| `assert_true(value, message="Assertion failed")` | `value`: 表达式；`message`: 错误信息 | 断言表达式为真 | 不满足则任务失败 |
| `assert_equal(actual, expected, message=None)` | `actual`: 实际值；`expected`: 期望值；`message`: 错误信息 | 断言两个值相等 | 不相等则任务失败 |

示例：

```python
assert_true(app.has_text("首页"), "没有进入首页")
assert_equal(1 + 1, 2)
test_pass()
```

## 底层 driver 能力

`driver` 是底层 Appium driver。平台推荐优先使用 `app.xxx`，但复杂场景可以直接调用 `driver`。

常见用法：

```python
driver.back()
driver.activate_app("com.shizhuang.duapp")
driver.terminate_app("com.shizhuang.duapp")
driver.find_element(AppiumBy.XPATH, '//*[@text="登录"]').click()
driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.TextView")
driver.get_page_source()
driver.get_screenshot_as_png()
```

注意：直接使用 `driver` 不一定会自动写平台日志，也不一定会把截图上传到任务详情。需要展示在任务详情里的截图，请使用 `app.screenshot()`。

## 可直接使用的对象

| 对象 | 作用 |
| --- | --- |
| `app` | 平台推荐 SDK |
| `driver` | 底层 Appium driver |
| `params` | 创建任务时传入的参数 |
| `task_id` | 当前任务 ID |
| `AppiumBy` | Appium 定位方式 |
| `datetime` / `date` / `timedelta` | 时间处理 |
| `Decimal` | 高精度数字 |

## 可用 Python 内置能力

脚本运行在受限沙箱里。当前可用的常见内置类型和函数如下。

### 类型

```python
bool
int
float
str
list
dict
tuple
set
frozenset
bytes
bytearray
complex
```

### 常用函数

```python
abs()
all()
any()
bin()
chr()
divmod()
enumerate()
filter()
format()
hex()
isinstance()
issubclass()
iter()
len()
map()
max()
min()
next()
oct()
ord()
pow()
print()
range()
reversed()
round()
slice()
sorted()
sum()
zip()
```

### 类型和属性相关

```python
type()
callable()
hasattr()
getattr()
setattr()
delattr()
```

### 可捕获异常

```python
Exception
ValueError
TypeError
KeyError
IndexError
AttributeError
RuntimeError
StopIteration
```

示例：

```python
texts = [item.text for item in app.find_all(AppiumBy.CLASS_NAME, "android.widget.TextView")]
assert_true(any("首页" in text for text in texts), "没有找到首页文本")
```

## 允许 import 的包

当前脚本只允许导入白名单内的标准库：

```python
import json
import re
import math
import random
import time
import uuid
import datetime
import decimal

from datetime import datetime, date, timedelta
from decimal import Decimal
```

不允许导入文件、系统、网络等高风险模块，例如：

```python
import os
import subprocess
import requests
```

如确实需要新增第三方包，建议先由平台后端统一安装依赖，再加入脚本导入白名单。

## 当前不开放的能力

出于安全和稳定性考虑，脚本当前不开放以下能力：

| 能力 | 说明 |
| --- | --- |
| 文件读写 | 不开放 `open()` |
| 动态执行代码 | 不开放 `eval()`、`exec()`、`compile()` |
| 任意系统调用 | 不允许 `os`、`subprocess` 等模块 |
| 任意网络请求 | 不允许直接导入 `requests` 等模块 |
| 任意第三方包 | 需要平台统一安装并加入白名单 |
| 相对导入 | 不支持 `from .xxx import yyy` |

如果自动化脚本确实需要新能力，建议把需求沉淀成平台 SDK 方法，而不是让业务脚本直接访问系统资源。

## 兼容旧脚本的全局方法

以下方法仍可使用，但新脚本建议改成 `app.xxx`：

| 旧方法 | 推荐替代 |
| --- | --- |
| `log(message, level="INFO")` | `app.log(message, level)` |
| `wait(seconds=1)` | `app.wait(seconds)` |
| `screenshot()` | `app.screenshot()` |
| `take_screenshot()` | `app.screenshot()` |
| `tap(x, y)` | `app.tap(x, y)` |
| `swipe(start_x, start_y, end_x, end_y, duration=500)` | `app.swipe(...)` |
| `input_text(text)` | `app.input_text(text)` |
| `press_key(keycode)` | `app.press_key(keycode)` |
| `assert_text(text)` | `app.assert_text(text)` |

## 推荐脚本结构

建议每个脚本按这个结构组织：

```python
import json
import re
from datetime import datetime

package = "com.shizhuang.duapp"

app.log("case start")

try:
    app.activate_app(package)
    app.wait(5)
    app.screenshot()

    app.wait_text("首页", timeout=15)
    test_pass()
except Exception as exc:
    app.log(f"case failed: {exc}", "ERROR")
    app.screenshot()
    test_fail(str(exc))
finally:
    app.terminate_app(package)
```

如果不想在失败时继续抛异常，可以使用 `test_fail()` 记录失败；如果希望任务直接进入失败状态，也可以让异常自然抛出。

## 完整示例

### Android/Harmony 示例

```python
import json
import re
from datetime import datetime

package = "com.shizhuang.duapp"

app.log("script start")
app.log(f"current time: {datetime.utcnow().isoformat()}")

data = json.loads('{"case": "duapp-smoke", "ok": true}')
assert_equal(data["ok"], True)
assert_true(re.match(r"duapp", data["case"]) is not None)

app.activate_app(package)
app.wait(5)
app.screenshot()

if app.has_text("同意"):
    app.click_text("同意", timeout=5)
    app.wait(2)
    app.screenshot()

if app.has_text("允许"):
    app.click_text("允许", timeout=5)
    app.wait(1)

source = app.source()
assert_true(len(source) > 0, "页面源码为空，App 可能未正常启动")

if app.has_text("搜索"):
    app.click_text("搜索", timeout=5)
else:
    app.log("未找到搜索入口，跳过点击", "WARN")

app.terminate_app(package)

app.log("script passed")
test_pass()
```

### iOS 设置页 smoke

完整文件见 `device-farm/scripts/examples/ios_settings_smoke.py`。该示例会启动系统设置、截图、读取页面 source，并点击 `通用` 或 `General`。

```python
app.log("iOS settings smoke start")

app.activate_app("com.apple.Preferences")
app.wait(2)
app.screenshot()

source = app.source()
assert_true(len(source) > 0, "iOS page source is empty")

if app.has_text("通用"):
    app.click_text("通用", timeout=8)
elif app.has_text("General"):
    app.click_text("General", timeout=8)
else:
    app.log("General entry was not found in Settings", "WARN")

app.screenshot()
test_pass()
```

## 常见建议

- 新脚本统一使用 `app.xxx`，减少风格混用。
- 包名写在脚本顶部，例如 `package = "com.shizhuang.duapp"`。
- 优先使用稳定的 ID 定位，其次使用 Accessibility ID，再考虑 XPath。
- `click_text` 适合快速冒烟测试，复杂页面建议使用明确定位方式。
- 每个关键步骤后可以加 `app.screenshot()`，便于失败后排查。
- 需要等待页面变化时优先用 `app.wait_text()`，少用固定长等待。
- 一个脚本可以控制多个 App，例如先打开系统设置，再打开被测 App。
- 如果脚本里直接调用 `driver`，建议额外用 `app.log()` 记录关键动作。

## 任务链路冒烟验证

项目内提供了一个任务链路冒烟脚本，用于验证创建脚本、创建任务、获取日志、取消任务等核心流程：

```bash
API_BASE=http://localhost:8003/api/v1 DEVICE_ID=<device-id> python3 device-farm/scripts/smoke_task_flow.py
```

如果本地开启了 API Key，再额外传入：

```bash
API_KEY=<api-key> API_BASE=http://localhost:8003/api/v1 DEVICE_ID=<device-id> python3 device-farm/scripts/smoke_task_flow.py
```
