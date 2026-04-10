import { useRef } from 'react'
import Editor, { OnMount } from '@monaco-editor/react'
import type { editor, languages, Position } from 'monaco-editor'

interface CodeEditorProps {
  value: string
  language?: string
  onChange?: (value: string) => void
  readOnly?: boolean
  height?: number | string
}

export default function CodeEditor({
  value,
  language = 'python',
  onChange,
  readOnly = false,
  height = 400,
}: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor

    // 配置 Python 语法高亮
    monaco.languages.registerCompletionItemProvider('python', {
      provideCompletionItems: (model: editor.ITextModel, position: Position) => {
        const word = model.getWordUntilPosition(position)
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        }
        const suggestions: languages.CompletionItem[] = [
          {
            label: 'driver',
            kind: monaco.languages.CompletionItemKind.Variable,
            insertText: 'driver',
            range,
          },
          {
            label: 'find_element',
            kind: monaco.languages.CompletionItemKind.Method,
            insertText: 'driver.find_element(by=By.${1}, value="${2}")',
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
          },
          {
            label: 'click',
            kind: monaco.languages.CompletionItemKind.Method,
            insertText: '.click()',
            range,
          },
          {
            label: 'send_keys',
            kind: monaco.languages.CompletionItemKind.Method,
            insertText: '.send_keys("${1}")',
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
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
        theme: 'vs',
      }}
    />
  )
}
