# 样例:技术选型调研 → 归档(完整走查)

> 给 agent 看的 few-shot。场景:用户问"PageIndex 这种检索方案对比我们现在的 RAG,值不值得换?"
> 每步标注 I/O。照此动作流执行。

## Phase 0 — vault 预检【读 /workspace/extra/vault】
```bash
rg -i -l "RAG|检索|PageIndex" /workspace/extra/vault
rg -i -l "RAG|PageIndex" /workspace/extra/vault/Wiki/Loom-Research
```
命中 `[[现有架构]]` 笔记 → 读取,顺 wikilink 爬;`Wiki/Loom-Research/` 无命中(归档将走 create)。
记:子问题"兼容性"已部分被既有笔记覆盖,仅需验证时效。

## Phase 1 — 需求拆解【推理】
- type=`tech-selection`,depth=`standard`,recency=技术(6 个月内)。
- 问题树(5 题,标 priority/depends_on):
  1. PageIndex 原理与定位(P0)
  2. 性能/准确率对比 RAG(P0)
  3. 适用边界与限制(P1)
  4. 与现有架构兼容性(P1,依赖①;vault 已部分覆盖)
  5. 成熟度/社区/维护(P2)

## Phase 2 — 信息采集【web egress + vault 复用】
- Q1:web 搜"PageIndex retrieval how it works"→ 官方文档(一手 ✅)。
- Q2:搜"PageIndex vs RAG benchmark"→ 广度命中博客;精准搜原始 benchmark → 2 独立源。
- 一次降级示例:某 benchmark 页 404 → 试 `web.archive.org` 取回快照。
- 各题 ≤3 轮;整体 web 调用控制在 standard ≤30(见 stop-criteria)。

## Phase 3 — 分析整合【推理 + 交叉验证】
- 性能:2 独立一手源一致 → ✅。
- 官方宣称 vs 社区实测分歧 → ⚠️,用 source-quality 矛盾格式标注:
  ```markdown
  关于"长文档准确率"存在分歧:
  - 来源A(官方文档, 2026-03):显著优于 RAG
  - 来源B(社区实测, 2026-05):特定语料下提升有限
  判断:采信条件并陈——长结构化文档收益明显,短文档收益有限 ⚠️
  ```

## Phase 4 — 报告生成【写作,主客分离】
```markdown
# PageIndex vs 现有 RAG — 技术选型
## TL;DR
初步判断:**长结构化文档场景值得试点,不建议全量替换**。理由:…;风险:…。  ← 带立场
## 原理 / 性能 / 限制 / 兼容性 / 成熟度
<各节,事实内联来源,推断标"个人评估">
## 局限性
时间范围截至 2026-06;benchmark 多为英文语料;未实测我们自有数据。
## 信息源
- [官方文档](...) ✅
- [benchmark A](...) / [社区实测 B](...) ⚠️
```

## Phase 5 — 自检
逐条过 SKILL §8 清单:TL;DR✅、源≥3✅、置信度标注✅、正反+局限✅、frontmatter 齐✅。

## Phase 6 — 归档【vault 去重 + selvage_call】
```bash
rg -i -l "pageindex|RAG 选型" /workspace/extra/vault/Wiki/Loom-Research/   # 未命中 → create
```
slug=`pageindex-vs-rag`。调用:
```
selvage_call(action="spool.archive", params={
  path: "Wiki/Loom-Research/pageindex-vs-rag.md",
  content: "---\ntype: research/tech-selection\ncreated: 2026-06-26\nupdated: 2026-06-26\ndomain: retrieval\nsources:\n  - https://...\ntags: [research, retrieval, rag]\n---\n# PageIndex vs 现有 RAG …(完整报告正文)\n",
  mode: "create"
})
```
返回 `{"status":"OK","result":"Wiki/Loom-Research/pageindex-vs-rag.md"}` → 告知用户已归档。
