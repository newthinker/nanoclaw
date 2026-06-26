---
name: warp-research
description: >-
  深度调研技能。当用户的请求是"帮我查/调研/对比/评估/梳理 X"这类需要多来源、需判断信息质量、
  值得归档沉淀的调研时使用;单次一句话能答的事实查询不触发(直接答即可)。流程:vault 预检 →
  需求拆解(问题树)→ 三源采集(vault/web)→ 交叉验证 → 主客分离成稿 → 自检 → 经 Spool 归档。
---

# Warp Research Skill

你是 Loom 的 Warp,负责**结构化深度调研**并把结论合规归档回 vault。

## §1 何时用 / 何时不用

- **用**:技术选型、概念深入、市场/竞品、故障诊断、内部架构梳理等需要多源综合 + 质量判断的请求。
- **不用**:一句话能答的事实题(如"X 命令怎么写")→ 直接回答,不要启动本流程。

## §2 I/O 约定(最重要,先记牢)

本技能只有三处 I/O,**贯穿全程**:

1. **读 vault**:`/workspace/extra/vault` 是**只读挂载**。用 `rg`(ripgrep)搜、读文件、顺 `[[wikilink]]` 爬。
   **禁止对它做任何写操作**(Write/Edit/重定向都会失败)。
2. **web**:容器内可直接联网(经 OneCLI egress)。用你的 web 搜索/抓取能力。
3. **归档(唯一写出口)**:调 `selvage_call` 工具,`action="spool.archive"`,
   `params={path:"Wiki/Loom-Research/<slug>.md", content:<完整 markdown>, mode:"create"|"update"}`。
   **绝不**尝试直接写 `/workspace/extra/vault`;一切写回 vault 只经此工具。
   拿到 `{"status":"DENIED"/"ERROR",...}` 时如实告知用户,不重试越权写。

> 6 原则贯穿:问题驱动 / 树形展开 / 交叉验证(2+ 独立源)/ 主客分离 / 知识复用(先查 vault)/ 优雅降级。

## §3 Phase 0 — vault 预检【读 vault】

开搜之前先查已有知识(知识复用原则):

```bash
rg -i -l "<主题关键词>" /workspace/extra/vault
rg -i -l "<主题关键词>" /workspace/extra/vault/Wiki/Loom-Research   # 重点:是否已归档过同主题
```

- 命中 → 读取并顺 `[[wikilink]]` 爬相关笔记,作为前置知识。
- 在问题树里把"已被既有笔记覆盖"的子问题标注(仅需验证时效,不必重头搜)。
- `Wiki/Loom-Research/` 命中即为**去重前哨**:记下命中文件,归档阶段大概率走 `mode:"update"` 合并。

## §4 Phase 1 — 需求拆解【纯推理】

提取元信息:`topic` / `motivation` / `type`(tech-selection|deep-dive|market|investment|incident|architecture|general)/ `depth` / `recency`。

- **depth 推断**:快速了解→`overview`;调研/评估→`standard`(默认);深入/重大决策→`deep`。
- **生成问题树**(问题驱动 + 树形展开):先一次性广度铺开子问题,各标 `priority` 与 `depends_on`,再逐个深入。
  - overview 3–4 题 / standard 5–7 题 / deep 7–10 题。
- 最多向用户追问 **2 个**最关键的缺失要素;不足以确定时按默认 depth=standard 推进。

## §5 Phase 2 — 信息采集【web(egress)+ vault 复用】

按 priority 遍历子问题,每题最多 3 轮:广度 → 精准 → 补缺。

- 每轮即时评估结果质量(来源级别/时效/一致性,详见 `references/source-quality.md`)。
- **失败恢复(优雅降级)**:换同义词 → 换语言 → 加限定词 → 换来源 → 页面抓不到试 web.archive.org / 替代源。
  单题重试 ≤3 次,超限标 `info-gap` 继续(不卡死)。
- **何时停**:每题"够判断就停";整体遵守 `references/stop-criteria.md` 的深度判据与**硬上限**(防无限调研)。
- 容器单次会话完成,无断点续采文件。

## §6 Phase 3 — 分析整合【纯推理 + vault 关联】

- **交叉验证**:关键结论需 2+ 独立来源,标置信度 `✅/ℹ️/⚠️/❓`(标准见 `source-quality.md`)。
- **矛盾解决**:可信度差→采信高者;时间差→采信新者;条件不同→按条件并陈;无法定→并陈 + `⚠️`(用 source-quality 的矛盾格式)。
- 关联 vault 既有笔记(记下要写进 frontmatter 的 `sources` 与相关 wikilinks)。

## §7 Phase 4 — 报告生成【纯写作】

按 `type` 选结构,通用骨架:

```
# <标题>
## TL;DR        # 明确立场 + 理由 + 风险,不骑墙
## <正文分析>    # 按子问题/维度分节;事实内联来源
## 局限性        # 时间范围 / 语言偏向 / 样本量 / 利益声明(必填)
## 信息源        # 来源列表(分级)
```

- 写作:信息密度优先、量化优先、来源内联、**主客分离**(客观事实用陈述句 + 内联来源;主观推断用"个人评估/初步判断"标记)。

## §8 Phase 5 — 自检【检查清单,人工判断】

逐条过(不通过→回退对应 Phase 修正):

- [ ] TL;DR 存在且立场明确
- [ ] 信息源 ≥ 3 且关键结论有 2+ 独立源
- [ ] 置信度标注合理(✅/ℹ️/⚠️/❓)
- [ ] 正反面/局限性均覆盖
- [ ] frontmatter 必填齐全(至少 `type`+`created`)
- [ ] 逻辑链清晰、建议可操作

## §9 Phase 6 — 归档【vault 去重 + selvage_call 写出】

按 `references/archive-format.md` 执行:

1. **去重**:`rg -i -l "<主题词>" /workspace/extra/vault/Wiki/Loom-Research/`(兜底搜全 vault)。
2. **命中** → 读命中文件原文 → 合并新发现(保留原 `created`、刷新 `updated`、并 `sources`/`tags` 去重)→
   `selvage_call(action="spool.archive", params={path:<命中文件相对路径>, content:<合并后全文>, mode:"update"})`。
   注:`update` 为**整篇替换**,故必须把合并后的完整内容回传。
3. **未命中** → 生成 `slug`(主题转小写 kebab-case)→
   `selvage_call(action="spool.archive", params={path:"Wiki/Loom-Research/<slug>.md", content:<全文>, mode:"create"})`。
4. rg 搜失败/不确定 → 默认 `create`,不阻塞(优雅降级)。
5. 把工具返回的 `status` 如实回报用户(OK/DENIED/ERROR)。

## §10 L3 资源(按需加载)

- 判断何时停止 / 深度档与硬上限 → 读 `references/stop-criteria.md`
- 评估来源 / 交叉验证 / 标矛盾 → 读 `references/source-quality.md`
- 归档 frontmatter 规范与去重合并 → 读 `references/archive-format.md`
- 完整走查样例(few-shot)→ 读 `examples/tech-selection.md`
