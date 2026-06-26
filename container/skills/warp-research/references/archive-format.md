# 归档格式与去重流程

调研产物经 `selvage_call(action="spool.archive", …)` 写到 `Wiki/Loom-Research/<slug>.md`。
**绝不直接写 `/workspace/extra/vault`**(只读)。

## frontmatter 规范

```yaml
---
type: research/<tech-selection|deep-dive|market|investment|incident|architecture|general>  # 必填
created: 2026-06-26      # 必填,ISO 日期
updated: 2026-06-26      # 合并(update)时刷新
domain: <主题域,如 RAG / 投资>
sources:                 # 引用来源 URL / vault 笔记
  - https://...
tags: [research, ...]
---
```

**最小契约 = `type` + `created`**(Spool 会校验 frontmatter 含这两项,缺失会被 DENIED)。

## slug 规则

主题转小写 **kebab-case**,去特殊字符。例:`PageIndex vs RAG` → `pageindex-vs-rag`。

## 去重 + create/update 流程(归档前必走)

1. **搜重**:
   ```bash
   rg -i -l "<slug 关键词>|<主题词>" /workspace/extra/vault/Wiki/Loom-Research/
   ```
   (兜底再搜全 `/workspace/extra/vault`,按 `type`+`domain` 二次搜降低漏判。)
2. **命中** → 读命中文件原文 → 合并新发现:
   - 保留原 `created`、刷新 `updated`、`sources`/`tags` 合并去重。
   - `selvage_call(action="spool.archive", params={path:<命中文件相对路径>, content:<合并后完整全文>, mode:"update"})`。
   - ⚠️ `update` 是**整篇替换**(底层 O_TRUNC),所以必须回传**合并后的完整内容**,不能只传增量。
3. **未命中** → 生成 slug →
   `selvage_call(action="spool.archive", params={path:"Wiki/Loom-Research/<slug>.md", content:<全文>, mode:"create"})`。
4. rg 搜失败 / 不确定 → 默认 `create`,不阻塞(优雅降级)。
5. 把工具返回 `status`(OK/DENIED/ERROR)如实回报用户;DENIED/ERROR 不重试越权写。

## 不做的事(容器 vault 只读所致)

- 不更新 MOC / 索引页、不往旧笔记追加反向引用、不写 Obsidian 隐藏注释——这些都要多文件写 vault,
  容器做不到;归档只产出/更新**单篇** `Wiki/Loom-Research/<slug>.md`。
