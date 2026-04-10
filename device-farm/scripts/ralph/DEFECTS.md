# 缺陷修复流程

所有缺陷修复都通过 ralph 工具自动执行。

## 如何提交缺陷

### 1. 创建缺陷 PRD

将缺陷信息写入 `scripts/ralph/prd.json`：

```json
{
  "projectName": "缺陷修复 - [日期]",
  "branchName": "[当前分支或修复分支]",
  "userStories": [
    {
      "id": "FIX-XXX",
      "title": "[缺陷标题]",
      "priority": 1,
      "passes": false,
      "acceptanceCriteria": [
        "[验收标准1]",
        "[验收标准2]",
        "Typecheck passes"
      ],
      "files": [
        "[相关文件路径1]",
        "[相关文件路径2]"
      ]
    }
  ]
}
```

### 2. 缺陷 ID 命名规范

| 类型 | 前缀 | 示例 |
|------|------|------|
| 安全漏洞 | FIX-SEC-XXX | FIX-SEC-001 |
| 功能缺陷 | FIX-BUG-XXX | FIX-BUG-001 |
| 性能问题 | FIX-PERF-XXX | FIX-PERF-001 |
| 代码审查问题 | FIX-CRITICAL-XXX | FIX-CRITICAL-001 |
| 文档问题 | FIX-DOC-XXX | FIX-DOC-001 |

### 3. 优先级定义

| 优先级 | 说明 | 处理时间 |
|--------|------|----------|
| 1 | Critical - 安全漏洞、数据丢失 | 立即 |
| 2 | High - 功能不可用 | 24小时内 |
| 3 | Medium - 功能受限但有 workaround | 3天内 |
| 4 | Low - 小问题、UI 优化 | 下个版本 |

### 4. 执行修复

```bash
cd device-farm/scripts/ralph
./ralph.sh --tool claude [迭代次数]
```

## 示例：代码审查缺陷修复

```json
{
  "projectName": "Phase 3 Code Review Fixes",
  "branchName": "phase3-features",
  "userStories": [
    {
      "id": "FIX-CRITICAL-001",
      "title": "JWT Secret 默认值不安全",
      "priority": 1,
      "passes": false,
      "acceptanceCriteria": [
        "JWT_SECRET_KEY 默认值为空",
        "启动时强制检查 JWT_SECRET_KEY",
        "Typecheck passes"
      ],
      "files": [
        "services/test-svc/app/config.py",
        "services/test-svc/app/main.py"
      ]
    }
  ]
}
```

## 缺陷来源

缺陷可来自以下渠道：

1. **代码审查** - 合并前的代码审查发现问题
2. **安全扫描** - SAST/DAST 工具扫描结果
3. **测试报告** - 自动化测试或手动测试发现
4. **用户反馈** - 生产环境问题报告
5. **监控告警** - 系统监控发现问题

## 工作流程

```
发现缺陷 → 记录到 prd.json → 运行 ralph → 自动修复 → 代码审查 → 合并
```

## 注意事项

1. 每个缺陷必须有明确的验收标准
2. 优先级高的缺陷先处理
3. 修复后必须通过 typecheck/lint/test
4. 保持提交粒度适中，一个缺陷一个提交
