# 笔记格式（note-format）

<!-- M3 的 TASK-004：命名规则、frontmatter 字段表、机器区边界与两级校验的唯一契约来源。 -->
<!-- prepare.py / verify.py（M3 的 TASK-005）与本文件必须逐字一致——它们三方共用这份规格。 -->

## 命名规则

笔记落在 vault 的 `Wiki/Macro/PBOC/` 下，文件名按 `period_type` 分五种：

| `period_type` | 文件名 | 例（period = `2026-06`） |
|---|---|---|
| `monthly` | `<YYYY-MM> 金融数据解读.md` | `2026-06 金融数据解读.md` |
| `q1` | `<YYYY> 一季度金融数据解读.md` | `2026 一季度金融数据解读.md` |
| `h1` | `<YYYY> 上半年金融数据解读.md` | `2026 上半年金融数据解读.md` |
| `q1_q3` | `<YYYY> 前三季度金融数据解读.md` | `2026 前三季度金融数据解读.md` |
| `annual` | `<YYYY> 全年金融数据解读.md` | `2026 全年金融数据解读.md` |

只有 `monthly` 带月份；其余四种**只取 `period` 的前四位年份**。

`prepare.py --print-name <contract>` 打印同一规则算出的文件名，SKILL.md 的 Step 3 用它取 `$N`。
**不要自己拼文件名**——拼错会让 `mode` 判断跟着错（见下面「`mode` 规则」）。

### 🔴 与上游 spec 的冲突及裁决

上游 spec（`2026-09-06-hestia-m3-warp-hestia-design.md`）在 §6 路径示例与 §8.2 判据 3 两处
写的是**带月份**的 `2026-06 上半年金融数据解读.md`，与上表**不一致**。

**裁决：取无月份版**（本文件上表即准）。依据：实施计划文档内部三处自洽地用无月份版——
`test_print_name` 的断言、冒烟命令里的 `$N`、以及冒烟判据里的笔记路径；而 spec 那两处是孤例。

⚠️ 这条冲突写在这里是**有意的**：它会在结转的集成冒烟里再被人看到一次，届时照本文件执行，
不要回头去按 spec 的写法改——否则 `prepare.py --print-name` 与冒烟判据会对不上。

## frontmatter 字段表

`prepare.py` 填，**模型一个字段都不碰**。

| 字段 | 来源 |
|---|---|
| `type: summary`、`domain: macro`、`created`、`updated`、`tags: [macro/pboc]`、`sources: [<article_id>]` | vault `CLAUDE.md` 要求的六个字段 |
| `period`、`period_type`、`published_at`、`caliber_version`、`extractor`、`source_url` | 契约 Meta |
| `supersedes_published_at` | 修订契约才有 |
| `m2_yoy`、`m1_yoy`、`scissors`、`tsf_stock_yoy`、`hh_mlt_monthly`、`hh_short_monthly`、`bill_ratio`、`temp_score`、`temp_known` | 派生指标（见 `glossary.md` 的四信号判定表与月均取法） |
| `signal_activation` / `signal_housing` / `signal_consumption` / `signal_credit` | `green` / `yellow` / `red` / `unknown` |
| `generated_by: warp-hestia@v1`、`contract_generated_by` | 后者取契约的 `generated_by`，实时与回放可分辨 |
| `reviewed: false`、`source: hestia` | 🔴 **Spool 强制写入**；`prepare.py` 不填，模型更不能写 |

## 正文骨架

```markdown
# 2026 年 8 月金融统计数据解读

<!-- machine-generated: begin -->
## 本期数据
（表：本期 vs 上期 vs 去年同期，含口径标注）
<!-- check: <sha256> -->

## 前 12 期
（表）
<!-- check: <sha256> -->

## 信号
活化 🔴 · 楼市 🟢 · 消费 🟢 · 信贷 🟡 · 温度 2/4

<!-- narrative -->
（模型叙述，按 methodology 的八问框架）
<!-- /narrative -->
<!-- seal: <sha256> -->
<!-- machine-generated: end -->

## 我的批注
（手写区，永不被覆盖）
```

## 🔴 两级校验：分段 `check` + 封条 `seal`

`verify.py` 在写回前重算这两级并与文件里的值比对，任一不符即**拒绝写回**。
两级的分工是**互补**的：`check` 防「改内容」，`seal` 防「删内容」。

### ① 分段 check `<!-- check: <sha256> -->`

- **位置**：紧跟一张数据表之后。
- **作用域**：从**上一个 `## ` 标题行**（含该行）起，到本 check 行之前（不含本行）的全部文本。
- **条数**：机器区内**恰好 2 条**——`## 本期数据` 与 `## 前 12 期` 各一条。
- 🔴 **`## 信号` 段不发 check 行**（依 spec §6.2 骨架）。**不要按 `## ` 标题数去推 check 行数**：
  机器区有 3 个 `## ` 而只有 2 条 check，「标题数 == check 数」这个判据装反了，
  会把一份完全合规的笔记判红。**条数写死为 2，不从文档结构推。**
- ⚠️ **`## ` 的计数有两个口径，都对，但都不能用来推 check 行数**：
  **机器区内**（`<!-- machine-generated: begin -->` → `end` 之间）是 **3** 个（`## 本期数据` / `## 前 12 期` / `## 信号`）；**整份骨架**是 **4** 个（再加区外的 `## 我的批注`）。
  而 check 恒为 **2**。⇒ 按机器区口径推得 3、按全文口径推得 4，**两个都错，后者错得更远**。
  这正是「写死条数」而不是「从结构推」的理由。

### ② 封条 seal `<!-- seal: <sha256> -->`

- **位置**：`<!-- machine-generated: end -->` **紧邻其上**。
- **条数**：**恰好 1 条**。
- **作用域**：从 `<!-- machine-generated: begin -->` 的**下一行**起、到本 seal 行**之前**的全部文本，
  **扣除** `<!-- narrative -->` 与 `<!-- /narrative -->` 之间的全部文本（**含这两行本身**）。

**封条防的是分段 check 防不住的两类篡改**：

| 篡改手法 | 分段 check | 封条 seal |
|---|---|---|
| 改一张表里的数字 | ✅ 拦下 | ✅ 拦下 |
| **删掉一条 check 行** | ❌ 没了就不比对了 | ✅ 覆盖文本变了 |
| **删掉一整段**（标题 + 表 + check 行） | ❌ 剩下的段各自仍自洽 | ✅ 覆盖文本变了 |
| **改 `## 信号` 段**（无 check 保护） | ❌ 不在任何 check 作用域内 | ✅ 覆盖文本变了 |

**narrative 段被扣除**，所以模型在叙述里写 `## ` 标题、写表格、随便改自己那一段，
都不会影响封条 —— 这正是 `methodology.md` 的八问框架允许你在叙述里用小标题的前提。

## `mode` 规则

- vault 的 `Wiki/Macro/PBOC/` 里**已有同名文件** ⇒ `update`（`prepare.py --existing <旧笔记>`
  已把「## 我的批注」之后的全部文本原样拼到新内容末尾）。
- **没有同名文件** ⇒ `create`。

`update` 时机器区整体重写、**批注区原样保留**；找不到 `## 我的批注` 标题则视为批注为空。

## 修订

契约 `is_revision: true` 时，frontmatter 会多一个 `supersedes_published_at`。
此时在正文一级标题（`# …金融统计数据解读`）**下面加一行**：

```markdown
> 本文取代 <supersedes_published_at 的日期> 版本。
```

这一行由 `prepare.py` 生成，模型不写、不删。
