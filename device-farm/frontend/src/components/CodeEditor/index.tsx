import { useRef } from 'react'
import Editor, { OnMount } from '@monaco-editor/react'
import type { editor, languages, Position } from 'monaco-editor'

interface CodeEditorProps {
  value: string
  language?: string
  onChange?: (value: string) => void
  readOnly?: boolean
  height?: number | string
  theme?: string
}

let pythonCompletionProviderRegistered = false

const createRange = (model: editor.ITextModel, position: Position, replaceFromDot = false) => {
  const word = model.getWordUntilPosition(position)
  const linePrefix = model.getLineContent(position.lineNumber).slice(0, position.column - 1)

  if (replaceFromDot) {
    const dotIndex = linePrefix.lastIndexOf('.')
    if (dotIndex >= 0) {
      return {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: dotIndex + 2,
        endColumn: position.column,
      }
    }
  }

  return {
    startLineNumber: position.lineNumber,
    endLineNumber: position.lineNumber,
    startColumn: word.startColumn,
    endColumn: word.endColumn,
  }
}

export default function CodeEditor({
  value,
  language = 'python',
  onChange,
  readOnly = false,
  height = 400,
  theme = 'vs',
}: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor

    const completionKind = monaco.languages.CompletionItemKind
    const snippetRule = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet

    if (pythonCompletionProviderRegistered) {
      return
    }
    pythonCompletionProviderRegistered = true

    monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.'],
      provideCompletionItems: (model: editor.ITextModel, position: Position) => {
        const linePrefix = model.getLineContent(position.lineNumber).slice(0, position.column - 1)
        const isAppMember = /(?:^|\W)app\.\w*$/.test(linePrefix)
        const isAppiumByMember = /(?:^|\W)AppiumBy\.\w*$/.test(linePrefix)
        const range = createRange(model, position, isAppMember || isAppiumByMember)

        if (isAppMember) {
          const appSuggestions: languages.CompletionItem[] = [
            {
              label: 'activate_app',
              kind: completionKind.Method,
              insertText: 'activate_app("${1:com.shizhuang.duapp}")',
              insertTextRules: snippetRule,
              documentation: '启动或拉起指定 App',
              range,
            },
            {
              label: 'launch_app',
              kind: completionKind.Method,
              insertText: 'launch_app("${1:com.shizhuang.duapp}")',
              insertTextRules: snippetRule,
              documentation: '启动指定 App；不传包名时拉起当前 session 绑定 App',
              range,
            },
            {
              label: 'terminate_app',
              kind: completionKind.Method,
              insertText: 'terminate_app("${1:com.shizhuang.duapp}")',
              insertTextRules: snippetRule,
              documentation: '退出或杀掉指定 App',
              range,
            },
            {
              label: 'close_app',
              kind: completionKind.Method,
              insertText: 'close_app("${1:com.shizhuang.duapp}")',
              insertTextRules: snippetRule,
              documentation: '关闭 App；带包名时等价于 terminate_app',
              range,
            },
            {
              label: 'restart_app',
              kind: completionKind.Method,
              insertText: 'restart_app("${1:com.shizhuang.duapp}", wait_seconds=${2:1})',
              insertTextRules: snippetRule,
              documentation: '退出指定 App，等待后重新启动',
              range,
            },
            {
              label: 'log',
              kind: completionKind.Method,
              insertText: 'log("${1:message}")',
              insertTextRules: snippetRule,
              documentation: '写入任务日志',
              range,
            },
            {
              label: 'wait',
              kind: completionKind.Method,
              insertText: 'wait(${1:1})',
              insertTextRules: snippetRule,
              documentation: '等待指定秒数',
              range,
            },
            {
              label: 'screenshot',
              kind: completionKind.Method,
              insertText: 'screenshot()',
              documentation: '截图并上传到任务详情',
              range,
            },
            {
              label: 'source',
              kind: completionKind.Method,
              insertText: 'source()',
              documentation: '获取当前页面源码/控件树',
              range,
            },
            {
              label: 'back',
              kind: completionKind.Method,
              insertText: 'back()',
              documentation: '返回键',
              range,
            },
            {
              label: 'home',
              kind: completionKind.Method,
              insertText: 'home()',
              documentation: 'Home 键',
              range,
            },
            {
              label: 'tap',
              kind: completionKind.Method,
              insertText: 'tap(${1:x}, ${2:y})',
              insertTextRules: snippetRule,
              documentation: '点击屏幕坐标',
              range,
            },
            {
              label: 'swipe',
              kind: completionKind.Method,
              insertText: 'swipe(${1:start_x}, ${2:start_y}, ${3:end_x}, ${4:end_y}, duration=${5:500})',
              insertTextRules: snippetRule,
              documentation: '滑动屏幕',
              range,
            },
            {
              label: 'input_text',
              kind: completionKind.Method,
              insertText: 'input_text("${1:text}")',
              insertTextRules: snippetRule,
              documentation: '向当前焦点输入文本',
              range,
            },
            {
              label: 'clear_text',
              kind: completionKind.Method,
              insertText: 'clear_text()',
              documentation: '清空当前焦点输入框，也可传定位参数清空指定元素',
              range,
            },
            {
              label: 'press_key',
              kind: completionKind.Method,
              insertText: 'press_key(${1:4})',
              insertTextRules: snippetRule,
              documentation: '发送 Android keycode，例如 4 是返回键',
              range,
            },
            {
              label: 'has_text',
              kind: completionKind.Method,
              insertText: 'has_text("${1:text}")',
              insertTextRules: snippetRule,
              documentation: '判断页面源码里是否包含文本',
              range,
            },
            {
              label: 'assert_text',
              kind: completionKind.Method,
              insertText: 'assert_text("${1:text}")',
              insertTextRules: snippetRule,
              documentation: '断言页面存在文本，不存在则失败',
              range,
            },
            {
              label: 'wait_text',
              kind: completionKind.Method,
              insertText: 'wait_text("${1:text}", timeout=${2:10})',
              insertTextRules: snippetRule,
              documentation: '等待文本出现，超时则失败',
              range,
            },
            {
              label: 'find',
              kind: completionKind.Method,
              insertText: 'find(AppiumBy.${1:ID}, "${2:value}", timeout=${3:10})',
              insertTextRules: snippetRule,
              documentation: '查找单个元素',
              range,
            },
            {
              label: 'find_all',
              kind: completionKind.Method,
              insertText: 'find_all(AppiumBy.${1:CLASS_NAME}, "${2:value}")',
              insertTextRules: snippetRule,
              documentation: '查找多个元素',
              range,
            },
            {
              label: 'wait_element',
              kind: completionKind.Method,
              insertText: 'wait_element(AppiumBy.${1:ID}, "${2:value}", timeout=${3:10})',
              insertTextRules: snippetRule,
              documentation: '等待元素出现并返回元素对象',
              range,
            },
            {
              label: 'exists',
              kind: completionKind.Method,
              insertText: 'exists(AppiumBy.${1:ID}, "${2:value}", timeout=${3:3})',
              insertTextRules: snippetRule,
              documentation: '判断元素是否存在',
              range,
            },
            {
              label: 'click',
              kind: completionKind.Method,
              insertText: 'click(AppiumBy.${1:ID}, "${2:value}", timeout=${3:10})',
              insertTextRules: snippetRule,
              documentation: '查找并点击元素',
              range,
            },
            {
              label: 'get_text',
              kind: completionKind.Method,
              insertText: 'get_text(AppiumBy.${1:ID}, "${2:value}", timeout=${3:10})',
              insertTextRules: snippetRule,
              documentation: '查找元素并返回文本',
              range,
            },
            {
              label: 'click_text',
              kind: completionKind.Method,
              insertText: 'click_text("${1:text}", timeout=${2:5})',
              insertTextRules: snippetRule,
              documentation: '按 text 或 content-desc 点击',
              range,
            },
            {
              label: 'tap_text',
              kind: completionKind.Method,
              insertText: 'tap_text("${1:text}", timeout=${2:5})',
              insertTextRules: snippetRule,
              documentation: '等价于 click_text',
              range,
            },
            {
              label: 'driver',
              kind: completionKind.Property,
              insertText: 'driver',
              documentation: '底层 Appium driver',
              range,
            },
          ]

          return { suggestions: appSuggestions }
        }

        if (isAppiumByMember) {
          const locatorSuggestions: languages.CompletionItem[] = [
            'ID',
            'XPATH',
            'ACCESSIBILITY_ID',
            'CLASS_NAME',
            'ANDROID_UIAUTOMATOR',
            'IOS_PREDICATE',
            'IOS_CLASS_CHAIN',
          ].map((label) => ({
            label,
            kind: completionKind.EnumMember,
            insertText: label,
            documentation: `AppiumBy.${label}`,
            range,
          }))

          return { suggestions: locatorSuggestions }
        }

        const globalRange = createRange(model, position)
        const suggestions: languages.CompletionItem[] = [
          {
            label: 'app',
            kind: completionKind.Variable,
            insertText: 'app',
            documentation: '平台推荐 SDK，输入 app. 可查看可用方法',
            range: globalRange,
          },
          {
            label: 'AppiumBy',
            kind: completionKind.Variable,
            insertText: 'AppiumBy',
            documentation: 'Appium 定位方式，输入 AppiumBy. 可查看定位类型',
            range: globalRange,
          },
          {
            label: 'driver',
            kind: completionKind.Variable,
            insertText: 'driver',
            documentation: '底层 Appium driver',
            range: globalRange,
          },
          {
            label: 'package',
            kind: completionKind.Snippet,
            insertText: 'package = "${1:com.shizhuang.duapp}"',
            insertTextRules: snippetRule,
            documentation: '定义被测 App 包名',
            range: globalRange,
          },
          {
            label: 'test_pass',
            kind: completionKind.Function,
            insertText: 'test_pass()',
            documentation: '标记测试通过',
            range: globalRange,
          },
          {
            label: 'test_fail',
            kind: completionKind.Function,
            insertText: 'test_fail("${1:reason}")',
            insertTextRules: snippetRule,
            documentation: '标记测试失败',
            range: globalRange,
          },
          {
            label: 'test_skip',
            kind: completionKind.Function,
            insertText: 'test_skip()',
            documentation: '标记测试跳过',
            range: globalRange,
          },
          {
            label: 'assert_true',
            kind: completionKind.Function,
            insertText: 'assert_true(${1:value}, "${2:message}")',
            insertTextRules: snippetRule,
            documentation: '断言表达式为真',
            range: globalRange,
          },
          {
            label: 'assert_equal',
            kind: completionKind.Function,
            insertText: 'assert_equal(${1:actual}, ${2:expected})',
            insertTextRules: snippetRule,
            documentation: '断言两个值相等',
            range: globalRange,
          },
          {
            label: 'duapp_smoke_template',
            kind: completionKind.Snippet,
            insertText: [
              'package = "com.shizhuang.duapp"',
              '',
              'app.log("script start")',
              'app.activate_app(package)',
              'app.wait(5)',
              'app.screenshot()',
              '',
              'if app.has_text("同意"):',
              '    app.click_text("同意", timeout=5)',
              '',
              'assert_true(len(app.source()) > 0, "页面源码为空")',
              'app.terminate_app(package)',
              'test_pass()',
            ].join('\n'),
            documentation: '得物 App 冒烟脚本模板',
            range: globalRange,
          },
        ]
        return { suggestions }
      },
    })
  }

  return (
    <Editor
      height={height}
      language={language}
      theme={theme}
      value={value}
      onChange={(v) => onChange?.(v || '')}
      onMount={handleEditorDidMount}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 2,
        wordWrap: 'on',
      }}
    />
  )
}
