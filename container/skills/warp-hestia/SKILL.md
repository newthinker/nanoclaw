---
name: warp-hestia
description: >-
  央行金融数据解读。当用户说「处理 hestia 队列」「生成金融数据解读」「解读这期央行数据」时使用：
  扫契约队列取最旧一份 → prepare.py 组装 → 只写叙述段 → verify.py 校验 → 经 Spool 写 Wiki/Macro/PBOC/。
  一次只处理一份。不用于回答一般宏观问题。
---

# Warp Hestia Skill

<!-- M3 的 TASK-004：本文件的六步与 §3 边界照需求文档原文，不得自行增删。 -->

## §1 I/O 约定（先记牢）

1. **队列**：`/workspace/extra/hestia-queue/`，**可写**。四个子目录 `pending/ processing/ done/ failed/`。
   契约 `<period>-<period_type>.json`，侧车 `<period>-<period_type>.history.json`，**成对移动**。
2. **vault**：`/workspace/extra/vault` 只读。用 `cat` / `rg` 读旧笔记与方法论；**绝不直接写**。
3. **写回（唯一写出口）**：`selvage_call(action="spool.archive", params={path, content, mode, source: "hestia"})`。
   拿到 `DENIED` / `ERROR` 原文回复用户，不重试。

### 模型边界（本 skill 最硬的一条）

你**只改** `<!-- narrative -->` 与 `<!-- /narrative -->` 之间的文本。除此之外：

- **不改数据表**（`## 本期数据` / `## 前 12 期` 两张表）
- **不改 frontmatter**（任何字段，包括你觉得填错了的）
- **不自己算指标**（剪刀差、月均、票据占比、温度全由 `prepare.py` 算好）
- **不写 `reviewed` / `source`**（Spool 会覆写）
- **不上网**——本 skill 只解读契约与侧车里的数据

改了上面任何一样，`verify.py` 会在写回前拦下来（§2 Step 5）。

## §2 六步（不跳步，不并行）

**Step 1 扫队列**

```bash
ls /workspace/extra/hestia-queue/pending/ | grep -v '\.history\.json$' | sort | head -1
```

空 ⇒ 回复「队列为空」，结束。

**Step 2 占位**

```bash
Q=/workspace/extra/hestia-queue; F=<上一步的文件名>; H=${F%.json}.history.json
[ -f $Q/pending/$H ] || { mv $Q/pending/$F $Q/failed/; echo "history 侧车缺失：用 atlas hestia contract emit --period … 补发"; exit; }
mv $Q/pending/$F $Q/pending/$H $Q/processing/
```

两个边界：

- **history 侧车缺失** ⇒ 契约**单独**移 `failed/`（没有侧车可移），提示用
  `atlas hestia contract emit --period …` 补发，结束。
- **同名已在 `processing/`** ⇒ 上次中断，**直接用 `processing/` 里那对，不重新占位**。

**Step 3 组装**

```bash
N=$(python3 /app/skills/warp-hestia/scripts/prepare.py --print-name $Q/processing/$F)
EXISTING=/workspace/extra/vault/Wiki/Macro/PBOC/$N
# 🔴 守卫判的是「文件**存在**」，不是「变量非空」——$EXISTING 是无条件赋值、恒非空。
# ⚠️ 刻意用显式 if/else 而不是数组：空数组的 "${ARR[@]}" 在 bash 3.2（macOS 自带）配 set -u
# 时会报 unbound variable，而 create 场景下它恰恰是空的。if/else 在 sh / bash 3.2 / zsh 都对。
if [ -f "$EXISTING" ]; then
  python3 /app/skills/warp-hestia/scripts/prepare.py $Q/processing/$F $Q/processing/$H --existing "$EXISTING" > /tmp/note.md
else
  python3 /app/skills/warp-hestia/scripts/prepare.py $Q/processing/$F $Q/processing/$H > /tmp/note.md
fi
```

🔴 **`$N` 必须由 `prepare.py --print-name` 打印，不要自己按命名规则拼**——命名规则有五种 `period_type` 分支且只有 `monthly` 带月份，拼错会让 Step 5 的 `mode` 跟着判错（把 `update` 判成 `create`，Spool 会拒绝覆盖已存在的笔记）。规则见 `references/note-format.md`「命名规则」，那里也说明了为什么由脚本打印。

🔴 **`--existing` 只在笔记已存在时才传**（M3 的 TASK-005 返工）：`$EXISTING` 是**无条件赋值**、恒非空，
若用 `${EXISTING:+…}` 判断，**create 场景（每期首次生成，笔记尚不存在）会把不存在的路径传进去**，
`prepare.py` 返回 2、产出 0 字节，按下面的失败分支每期首次都被移进 `failed/`。
⇒ 判据必须是 `[ -f "$EXISTING" ]`。**已有笔记的 update 场景本来就是好的**，坏的只有新笔记。

`prepare.py` **退出码非零** ⇒ 把 stderr **原文**回复用户，契约与侧车**对移 `failed/`**，结束。

输出已含：完整 frontmatter、机器区数据表（带 `<!-- check: … -->` 校验行）、四信号与温度、
`<!-- narrative -->` 段落里的**判读提示**、以及批注区（若有旧笔记）。

**Step 4 写叙述**

读 `references/methodology.md`。**只改** `<!-- narrative -->` 与 `<!-- /narrative -->` 之间的文本：
按八问框架写，每一问引用数据表里的数字，不自己算、不改表、不动 frontmatter。写完存回 `/tmp/note.md`。

**Step 5 校验并写回**

```bash
python3 /app/skills/warp-hestia/scripts/verify.py /tmp/note.md || { echo "数据段被改动，拒绝写回"; exit; }
```

`verify.py` **退出码非零** ⇒ **拒绝写回**，把差异回复用户。
🔴 **此时契约与侧车留在 `processing/`，不移 `failed/`**——数据段被改是**这一轮叙述**的问题，
契约本身没毛病；移 `failed/` 会让一份好契约需要人工捞回。留在 `processing/` 则下一次会话按
Step 2 的「同名已在 processing ⇒ 直接用那对」自然重试。

校验通过后：`mode` 取值——**对文件求值**：`[ -f "$EXISTING" ] && mode=update || mode=create`。
⚠️ 与 Step 3 的守卫**同源同判据**：判「文件存在」而不是「变量非空」，否则每期首次都会误判成 `update`，
Spool 会因目标不存在而拒绝。

```
selvage_call(action="spool.archive",
             params={path: "Wiki/Macro/PBOC/$N", content: <文件全文>, mode, source: "hestia"})
```

**Step 6 收尾**

- `OK` ⇒ `mv $Q/processing/$F $Q/processing/$H $Q/done/`；回复「已写入 Wiki/Macro/PBOC/$N，队列还剩 N 份」。
- `DENIED` / `ERROR` ⇒ `mv $Q/processing/$F $Q/processing/$H $Q/failed/`；把返回**原文**回复用户，**不重试**。

### 失败分支一览（四条，别记混）

| 在哪一步 | 触发 | 队列处置 | 回复什么 |
|---|---|---|---|
| Step 2 | history 侧车缺失 | 契约**单独**移 `failed/` | 补发命令 |
| Step 3 | `prepare.py` 退出码非零 | 契约与侧车**对移 `failed/`** | stderr **原文** |
| Step 5 | `verify.py` 退出码非零 | 🔴 **留在 `processing/`**，不移 | 差异；下次会话自然重试 |
| Step 6 | `spool.archive` 返回 `DENIED` / `ERROR` | 契约与侧车**对移 `failed/`** | 返回**原文**，不重试 |

## §3 不做

- 不处理第二份（用户再说一句才继续）
- 不改数据表、不改 frontmatter、不自己算指标
- 不写 `reviewed` / `source`（Spool 会覆写）
- 不上网查资料——本 skill 只解读契约与侧车里的数据
