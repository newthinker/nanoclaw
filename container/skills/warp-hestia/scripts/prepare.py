#!/usr/bin/env python3
"""契约 + 侧车 → 笔记（frontmatter + 机器区 + 判读提示 + 批注区）。M3 的 TASK-005。

只用标准库。派生指标与 Atlas 的 Evaluate 同源：_mom 优先 → monthly _ytd ÷ MM → 3/6/9/12。

两级校验（规格以 references/note-format.md 为准，三处逐字一致）：
  ① 分段 check `<!-- check: <sha256> -->`：覆盖「从上一个 `## ` 标题行起到本行之前」。
     机器区内**恰好 2 条**（`## 本期数据`、`## 前 12 期`）；`## 信号` 段**不发**。
     🔴 条数写死为 2，**不从 `## ` 标题数推**——机器区有 3 个 `## `、整份骨架 4 个，两个口径推出来都错。
  ② 封条 seal `<!-- seal: <sha256> -->`：`<!-- machine-generated: end -->` 紧邻其上，**恰好 1 条**，
     覆盖「begin 的下一行 → seal 行之前」，**扣除** narrative 块（含 `<!-- narrative -->` /
     `<!-- /narrative -->` 两行本身）。封条是「删除类篡改」的唯一防线。
"""
import argparse
import datetime
import hashlib
import json
import math
import unicodedata
import re
import sys

MONTHS = {"q1": 3, "h1": 6, "q1_q3": 9, "annual": 12}
UNITS = {"balance": "万亿元", "flow": "亿元", "ratio": "百分数"}
# 信号四态 → 图标。判读提示与 `## 信号` 段共用同一份，两处必须一致。
EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⬜"}

NAME_SUFFIX = {"q1": "一季度", "h1": "上半年", "q1_q3": "前三季度", "annual": "全年"}

BEGIN = "<!-- machine-generated: begin -->"
END = "<!-- machine-generated: end -->"
NARR_OPEN = "<!-- narrative -->"
NARR_CLOSE = "<!-- /narrative -->"
ANNOTATION_HEADING = "## 我的批注"

PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


# ── 派生指标（与 Atlas internal/hestia/signals.go 的 Evaluate 同源）──────────────

def months_in_period(period, ptype):
    """期内月数。monthly 取 period 的 MM；解析不出、越界（00/13）、长度不对、
    未知 period_type ⇒ 返回 0（调用方视为缺失，**绝不拿它做除数**）。"""
    if ptype in MONTHS:
        return MONTHS[ptype]
    if ptype != "monthly":
        return 0
    m = PERIOD_RE.match(period or "")
    if not m:
        return 0
    mm = int(m.group(2))
    return mm if 1 <= mm <= 12 else 0


def monthly_average(values, ytd, mom, period, ptype):
    """流量字段的月均 → (value, ok)。_mom 非空 ⇒ 就是它（月数 1，不再除）；
    否则用 _ytd ÷ 期内月数。月数为 0 ⇒ (0, False)，不除——否则 ÷0 得 ±Inf，
    会被阈值判定当成「很大」的月均而误判绿灯。"""
    if values.get(mom) is not None:
        return values[mom], True
    if values.get(ytd) is None:
        return 0, False
    n = months_in_period(period, ptype)
    if n == 0:
        return 0, False
    return values[ytd] / n, True


def same_caliber_pair(values, a_ytd, a_mom, b_ytd, b_mom):
    """在 (_mom, _mom) 与 (_ytd, _ytd) 里取第一对都非空的；**_mom 优先**。
    一个当月一个累计的比值没有意义 ⇒ 不允许跨口径配对。"""
    for a, b in ((a_mom, b_mom), (a_ytd, b_ytd)):
        if values.get(a) is not None and values.get(b) is not None:
            return values[a], values[b], True
    return 0, 0, False


def _eval_activation(values, sig):
    m1, m2 = values.get("m1_yoy"), values.get("m2_yoy")
    if m1 is None or m2 is None:
        return "unknown", None
    d = m1 - m2
    if d >= sig["scissors_active"]:
        return "green", d
    if d <= sig["scissors_sink"]:
        return "red", d
    return "yellow", d


def _eval_threshold(values, ytd, mom, period, ptype, warm):
    """楼市 / 消费两个信号**没有黄灯**：月均 ≥ warm 绿，否则红。"""
    v, ok = monthly_average(values, ytd, mom, period, ptype)
    if not ok:
        return "unknown", None
    return ("green" if v >= warm else "red"), v


def _eval_credit(values, sig):
    bill, total, ok = same_caliber_pair(values, "loan_bill_ytd", "loan_bill_mom",
                                        "loan_corp_total_ytd", "loan_corp_total_mom")
    if not ok or total == 0:
        return "unknown", None
    r = bill / total * 100
    if r < sig["bill_ratio_healthy"]:
        return "green", r
    if r >= sig["bill_ratio_severe"]:
        return "red", r
    return "yellow", r


def evaluate(values, period, ptype, sig):
    """四信号 + 温度。🔴 输入缺失是 `unknown`（四态），不是红。
    温度 = 已知信号里的绿灯数 / 非 unknown 的信号数——**有 unknown 时分母减一，不假装是 4**。"""
    activation, scissors = _eval_activation(values, sig)
    housing, hh_mlt = _eval_threshold(values, "loan_hh_mlt_ytd", "loan_hh_mlt_mom",
                                      period, ptype, sig["hh_mlt_monthly_warm"])
    consumption, hh_short = _eval_threshold(values, "loan_hh_short_ytd", "loan_hh_short_mom",
                                            period, ptype, sig["hh_short_monthly_warm"])
    credit, bill_ratio = _eval_credit(values, sig)

    known = score = 0
    for s in (activation, housing, consumption, credit):
        if s == "unknown":
            continue
        known += 1
        if s == "green":
            score += 1

    return {"activation": activation, "housing": housing, "consumption": consumption,
            "credit": credit, "score": score, "known": known,
            "scissors": scissors, "hh_mlt_monthly": hh_mlt,
            "hh_short_monthly": hh_short, "bill_ratio": bill_ratio}


# ── 命名与格式 ────────────────────────────────────────────────────────────────

def note_name(period, ptype):
    """命名规则见 references/note-format.md。**只有 monthly 带月份**；其余四种只取年份。
    与上游 spec §6 的带月份写法冲突，取无月份版（实施计划三处自洽，裁决见 note-format.md）。"""
    if ptype == "monthly":
        return "%s 金融数据解读.md" % period
    year = (period or "")[:4]
    return "%s %s金融数据解读.md" % (year, NAME_SUFFIX.get(ptype, ""))


def fmt(v):
    """整数打整数，非整数保留两位。给人看的表，不追求与 Atlas fmtNum 逐字一致。"""
    if v is None:
        return "—"
    r = round(float(v), 2)
    return str(int(r)) if r == int(r) else ("%.2f" % r)


# ── frontmatter ──────────────────────────────────────────────────────────────

def build_frontmatter(contract, derived, now):
    """spec §6.1 全表，有序 list[(k, v)]。🔴 **不含 reviewed / source**（Spool 强制覆写）。"""
    fields = [
        ("type", "summary"),
        ("domain", "macro"),
        ("created", now),
        ("updated", now),
        ("tags", "[macro/pboc]"),
        ("sources", "[%s]" % contract["article_id"]),
        ("period", contract["period"]),
        ("period_type", contract["period_type"]),
        ("published_at", contract["published_at"]),
        ("caliber_version", contract["caliber_version"]),
        ("extractor", contract["extractor"]),
        ("source_url", contract["source_url"]),
    ]
    if contract.get("is_revision") and contract.get("supersedes_published_at"):
        fields.append(("supersedes_published_at", contract["supersedes_published_at"]))

    data = contract["data"]
    fields += [
        ("m2_yoy", fmt(data.get("m2_yoy"))),
        ("m1_yoy", fmt(data.get("m1_yoy"))),
        ("scissors", fmt(derived["scissors"])),
        ("tsf_stock_yoy", fmt(data.get("tsf_stock_yoy"))),
        ("hh_mlt_monthly", fmt(derived["hh_mlt_monthly"])),
        ("hh_short_monthly", fmt(derived["hh_short_monthly"])),
        ("bill_ratio", fmt(derived["bill_ratio"])),
        ("temp_score", str(derived["score"])),
        ("temp_known", str(derived["known"])),
        ("signal_activation", derived["activation"]),
        ("signal_housing", derived["housing"]),
        ("signal_consumption", derived["consumption"]),
        ("signal_credit", derived["credit"]),
        ("generated_by", "warp-hestia@v1"),
        ("contract_generated_by", contract["generated_by"]),
    ]
    return fields


# ── 两张表 ───────────────────────────────────────────────────────────────────

# (显示名, _ytd 键, _mom 键, 单位类别)；_ytd/_mom 同名表示该字段无口径之分
ROWS = [
    ("社融存量同比", "tsf_stock_yoy", "tsf_stock_yoy", "ratio"),
    ("M2 同比", "m2_yoy", "m2_yoy", "ratio"),
    ("M1 同比", "m1_yoy", "m1_yoy", "ratio"),
    ("住户中长期贷款", "loan_hh_mlt_ytd", "loan_hh_mlt_mom", "flow"),
    ("住户短期贷款", "loan_hh_short_ytd", "loan_hh_short_mom", "flow"),
    ("企业贷款合计", "loan_corp_total_ytd", "loan_corp_total_mom", "flow"),
    ("票据融资", "loan_bill_ytd", "loan_bill_mom", "flow"),
]


def _pick(values, ytd, mom):
    """取值并报出用的是哪个口径。_mom 优先，与月均取法同序。"""
    dual = mom != ytd          # 同名 ⇒ 该字段无 _ytd/_mom 之分，不报口径
    if values.get(mom) is not None:
        return values[mom], ("_mom" if dual else "")
    if values.get(ytd) is not None:
        return values[ytd], ("_ytd" if dual else "")
    return None, ""


def pair_key(contract):
    """契约在侧车里的标识：`<period>-<period_type>`，与 atlas `history.go` 写出的 `for` 同构。"""
    return "%s-%s" % (contract["period"], contract["period_type"])


def assert_pair(contract, history):
    """🔴 校验契约与侧车**确实是一对**（M3 的 TASK-005 返工，F2）。

    缺陷形态：本函数不存在时，`prepare.py` 从 history 上只读 `same_type`，
    侧车顶层的 `for` 字段**被读 0 次** ⇒ 错配的一对喂进去，prepare 与 verify **双双 exit 0**，
    而 frontmatter / 标题 / 四信号 / 温度全对（都来自契约）、**两张表全错**（都来自侧车）
    ——笔记自洽地看起来完全正常。实测：`2026-06-h1.json × 2025-12-annual.history.json`
    产出 3161 字节、verify exit 0，笔记自称 `2026-06/h1` 而前 12 期表全是 annual 期次，
    连本期数据表的「上期」列也变成了 2024-12。

    ⚠️ **污染面不止「前 12 期」表**：`render_table_current` 的上期/去年同期两列同样取自
    `same_type`（`series[0]` 就是上期），而那是解读的起点。

    `for` 是这条链路上**唯一能机器判定「这两个文件是一对」的事实**。
    ⚠️ 判据是 `for == period + "-" + period_type`，**不是文件名**——修订夹具叫
    `2025-12-annual-rev.*` 而它的 `for` 是 `2025-12-annual`，拿文件名判会误拒。

    返回 (ok, message)；不成立时由 main 打印 message 并 exit 2。
    """
    want = pair_key(contract)
    got = history.get("for")
    if got == want:
        return True, ""
    return False, ("契约与侧车不是一对：契约是 %s，而侧车的 for 是 %r。\n"
                   "两张表全部取自侧车，错配会产出「自洽但表全错」的笔记（frontmatter 与信号来自契约、"
                   "两张表来自侧车），故拒绝。" % (want, got))


def _series(history):
    """🔴 **一律取 `same_type`**——它就是「同类型前 12 期」。
    `monthly_recent` 在 `period_type == monthly` 时被**刻意省略**（Atlas 侧 `omitzero`，
    见 internal/hestia/history.go 的注释）：对 monthly 契约，`same_type` 本身即月度序列；
    `monthly_recent` 只是非 monthly 期次的近月补充上下文，不是本表的数据源。
    按期次倒序，保证确定性。"""
    return sorted(history.get("same_type") or [], key=lambda e: e["meta"]["period"], reverse=True)


def _year_ago(period):
    m = PERIOD_RE.match(period or "")
    return None if not m else "%04d-%s" % (int(m.group(1)) - 1, m.group(2))


def render_table_current(contract, history):
    """本期 vs 上期 vs 去年同期，**含口径标注**——`caliber_version` 不同的列要标出来，
    它是 glossary『跨口径对比禁忌』与 spec §9 风险表的落地载体。"""
    series = _series(history)
    prev = series[0] if series else None
    ya_period = _year_ago(contract["period"])
    year_ago = next((e for e in series if e["meta"]["period"] == ya_period), None)

    cur_cal = contract["caliber_version"]

    def head(label, entry):
        if entry is None:
            return "%s（无）" % label
        cal = entry["meta"]["caliber_version"]
        mark = "" if cal == cur_cal else " ⚠️口径 %s" % cal
        return "%s %s%s" % (label, entry["meta"]["period"], mark)

    lines = [
        "| 指标 | 单位 | 本期 %s（口径 %s） | %s | %s |" % (
            contract["period"], cur_cal, head("上期", prev), head("去年同期", year_ago)),
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for label, ytd, mom, unit in ROWS:
        cur, cal_mark = _pick(contract["data"], ytd, mom)
        pv = _pick(prev["data"], ytd, mom)[0] if prev else None
        yv = _pick(year_ago["data"], ytd, mom)[0] if year_ago else None
        name = label + ("（%s）" % cal_mark.lstrip("_") if cal_mark else "")
        lines.append("| %s | %s | %s | %s | %s |" % (name, UNITS[unit], fmt(cur), fmt(pv), fmt(yv)))

    lines.append("")
    if prev is not None and year_ago is not None and prev["meta"]["period"] == year_ago["meta"]["period"]:
        lines.append("> 注：`%s` 的同类型上一期就是去年同期（`same_type` 是逐年的），故两列相同。"
                     % contract["period_type"])
    lines.append("> 口径标注：本期 `caliber_version` 为 `%s`；标 ⚠️ 的列口径不同，**不可直接做同比**。"
                 % cur_cal)
    lines.append("> 流量字段的 `_ytd`（年初累计）与 `_mom`（当月）不可混比，列名括号里标了取的哪一种。")
    return "\n".join(lines) + "\n"


def render_table_history(history, ptype=None):
    """前 12 期。数据**取自侧车的 `same_type`**，有多少渲染多少，
    不自己查库、不补齐、不截断到别的条数。`ptype` 仅为兼容保留，不参与取数。"""
    series = _series(history)
    lines = ["| 期次 | 口径 | M1 同比 | M2 同比 | 住户中长期贷款 | 住户短期贷款 |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for e in series:
        d, m = e["data"], e["meta"]
        hh_mlt, _ = _pick(d, "loan_hh_mlt_ytd", "loan_hh_mlt_mom")
        hh_short, _ = _pick(d, "loan_hh_short_ytd", "loan_hh_short_mom")
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            m["period"], m["caliber_version"], fmt(d.get("m1_yoy")), fmt(d.get("m2_yoy")),
            fmt(hh_mlt), fmt(hh_short)))
    lines.append("")
    lines.append("> 共 %d 期，取自侧车的 `same_type`（同类型前 12 期，有多少列多少）。" % len(series))
    return "\n".join(lines) + "\n"


# ── 校验行 ───────────────────────────────────────────────────────────────────

def with_check(section_md):
    """追加分段 check。作用域 = 传入的整段文本（调用方保证它从 `## ` 标题行起）。"""
    digest = hashlib.sha256(section_md.encode("utf-8")).hexdigest()
    return section_md + "<!-- check: %s -->\n" % digest


def seal_digest(md):
    """封条覆盖范围：`begin` 的**下一行**起、到 seal 行**之前**，
    **扣除** narrative 块（含 `<!-- narrative -->` / `<!-- /narrative -->` 两行本身）。"""
    body = md.split(BEGIN + "\n", 1)[1]
    body = body.split("<!-- seal: ", 1)[0]
    if NARR_OPEN in body and NARR_CLOSE in body:
        head, rest = body.split(NARR_OPEN, 1)
        _, tail = rest.split(NARR_CLOSE, 1)
        body = head + tail.lstrip("\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── 批注区 ───────────────────────────────────────────────────────────────────

def extract_annotations(existing_md):
    """取旧笔记 `## 我的批注` 之后的原文。找不到该标题 ⇒ 视为空（spec §6.3），
    不报错、不吞内容。"""
    if not existing_md or ANNOTATION_HEADING not in existing_md:
        return ""
    return existing_md.split(ANNOTATION_HEADING, 1)[1].lstrip("\n")


# ── 判读提示 ─────────────────────────────────────────────────────────────────

def reading_hints(contract, derived):
    """写进 narrative 段的判读提示（reviewer O4：这一段不能是空的）。"""
    return (
        "（判读提示——按 `references/methodology.md` 的**八问**框架写，"
        "每一问引用上面表里的数字，不自己算、不改表、不动 frontmatter。）\n"
        "\n"
        "- **排版**（见 `references/methodology.md` 的「排版纪律」）：每问先写一句**加粗结论**（≤30 字），"
        "三值以上的对比进小表，论证段 ≤150 字，字段名统一放段末的 `<sub>` 行、"
        "**不要嵌在句子中间**；缺失与警示用 `⚠️` 单起一行。\n"
        "- 本期四信号：活化 %s / 楼市 %s / 消费 %s / 信贷 %s，温度 **%d/%d**。\n"
        "- 剪刀差 `scissors` = %s；`caliber_version` = `%s`，"
        "**跨口径的期次不要做同比**（见 `references/glossary.md`）。\n"
        "- 已知信号 %d 个 —— **温度的分母是 `temp_known`，不是恒定的 4**；%s。\n"
        "- 八问顺序：经济扩张还是收缩 / 房地产是否复苏 / 消费是否回暖 / 企业扩张还是维持 / "
        "贷款有没有水分 / 钱去哪儿了 / 谁在加杠杆 / 钱贵不贵。\n"
    ) % (EMOJI[derived["activation"]], EMOJI[derived["housing"]], EMOJI[derived["consumption"]],
         EMOJI[derived["credit"]], derived["score"], derived["known"],
         fmt(derived["scissors"]), contract["caliber_version"], derived["known"],
         "本期有信号为 unknown，写作时要点名是哪个字段缺了"
         if derived["known"] < 4 else "本期四个信号都已知")


# ── 图表（M3 后续，2026-09-16）────────────────────────────────────────────────
#
# 🔴 图表段**不发 check 行**，沿 `## 信号` 段的先例——note-format.md 的两级校验表里
# 「改 `## 信号` 段（无 check 保护）」那一行写明：封条 seal 覆盖机器区减叙述段，
# 改内容与删整段都拦得住。check 行数因此**继续写死为 2**，不随图表段增减。
#
# 渲染分工（2026-09-16 裁决）：趋势用 mermaid 折线（看得出拐点），阈值对比用文本条
# （永不会坏、git diff 干净、任何 markdown 阅读器里都一样）。Obsidian 1.12 内置
# mermaid 且支持 xychart-beta，不需要 Charts 插件。

BAR_FULL, BAR_EMPTY = "█", "░"

SIGNAL_LABEL = {"activation": "活化", "housing": "楼市",
                "consumption": "消费", "credit": "信贷"}


def pad(text, width):
    """按**显示列宽**右补空格。中文/全角占 2 列，`%-Ns` 按字符数补齐会让列参差，
    而文本条的全部价值就是一眼扫过去。超宽不截断——截断会把「未贴现承兑汇票」
    砍成半个词，比不对齐更糟。"""
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(0, width - w)


def bar(ratio, width=10):
    """把 0..1 画成方块条。None 与越界都按边界处理——条是给人扫一眼的，
    不该因为一个缺失值就抛异常把整篇笔记搞没。"""
    if ratio is None:
        return BAR_EMPTY * width
    r = min(1.0, max(0.0, float(ratio)))
    full = int(round(r * width))
    return BAR_FULL * full + BAR_EMPTY * (width - full)


def achievement(name, value, sig):
    """「距绿灯多远」，绿灯即 1.0。四个信号的判定形状不同，这里统一成一个可比的数：

      activation  两条线（沉淀 / 活化）⇒ 落在区间内按线性位置
      housing     一条正阈值        ⇒ 值 ÷ 阈值，截断到 [0,1]
      consumption 阈值是 0          ⇒ 非此即彼（该信号本就没有黄灯）
      credit      两条线（健康 / 严重）⇒ 越小越好，反向线性

    ⚠️ 红灯也给距离而不是一律 0：楼市 368.67/2000 = 18% 比「0%」有用得多。
    返回 None 表示输入缺失（对应 unknown），调用方画空条并标 n/a。"""
    if value is None:
        return None
    v = float(value)
    if name == "activation":
        sink, active = float(sig["scissors_sink"]), float(sig["scissors_active"])
        if v >= active:
            return 1.0
        if v <= sink:
            return 0.0
        return (v - sink) / (active - sink)
    if name == "credit":
        healthy, severe = float(sig["bill_ratio_healthy"]), float(sig["bill_ratio_severe"])
        if v < healthy:
            return 1.0
        if v >= severe:
            return 0.0
        return (severe - v) / (severe - healthy)
    warm = float(sig["hh_mlt_monthly_warm"] if name == "housing" else sig["hh_short_monthly_warm"])
    if warm == 0:
        return 1.0 if v >= 0 else 0.0
    return min(1.0, max(0.0, v / warm))


def render_signal_bars(derived, sig):
    """四信号距绿灯多远。每个信号一行，同一行内给出值、条、达成度、阈值与灯。"""
    rows = [
        ("activation", "剪刀差", derived.get("scissors"), "pct",
         "沉淀线 %s / 活化线 %s" % (fmt(sig["scissors_sink"]), fmt(sig["scissors_active"]))),
        ("housing", "住户中长期月均", derived.get("hh_mlt_monthly"), "亿元",
         "暖身线 %s" % fmt(sig["hh_mlt_monthly_warm"])),
        ("consumption", "住户短期月均", derived.get("hh_short_monthly"), "亿元",
         "暖身线 %s" % fmt(sig["hh_short_monthly_warm"])),
        ("credit", "票据占企业新增", derived.get("bill_ratio"), "%",
         "健康线 %s / 严重线 %s" % (fmt(sig["bill_ratio_healthy"]), fmt(sig["bill_ratio_severe"]))),
    ]
    lines = ["", "**达成度**：绿灯即 100%；红灯也按距绿灯的远近给值，不一律记 0。", "", "```"]
    for key, metric, value, unit, thresh in rows:
        a = achievement(key, value, sig)
        pct = "n/a " if a is None else "%3d%%" % int(round(a * 100))
        lines.append("%s  %s%s %s  %s  %s  %s  %s" % (
            SIGNAL_LABEL[key], pad(metric, 16), "%9s" % fmt(value), pad(unit, 4),
            bar(a), pct, thresh, EMOJI[derived[key]]))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _xychart(title, labels, values, yname):
    """一张 mermaid 折线。y 轴范围由数据算，留一成余量，保证确定性。"""
    lo, hi = min(values), max(values)
    pad = max(1.0, (hi - lo) * 0.1)
    return "\n".join([
        "```mermaid",
        "xychart-beta",
        '    title "%s"' % title,
        "    x-axis [%s]" % ", ".join(labels),
        '    y-axis "%s" %d --> %d' % (yname, math.floor(lo - pad), math.ceil(hi + pad)),
        "    line [%s]" % ", ".join(fmt(v) for v in values),
        "```",
        "",
    ])


def _trend_points(contract, history, pick):
    """侧车的同类型历史 + **本期**，按期次升序。

    🔴 本期必须由契约补在末尾：侧车的 `same_type` 来自 `Store.Preceding`，语义是
    「period < 本期」，只补历史不含当期 ⇒ 不补的话图上看不到最新那个点，
    而最新那个点正是读者最关心的。

    取不到值的期次**跳过**（不补零、不插值）：补零会在图上画出一个假的谷底。"""
    pts = []
    for e in sorted(history.get("same_type") or [], key=lambda x: x["meta"]["period"]):
        v = pick(e["data"], e["meta"]["period"], contract["period_type"])
        if v is not None:
            pts.append((e["meta"]["period"], v))
    cur = pick(contract["data"], contract["period"], contract["period_type"])
    if cur is not None:
        pts.append((contract["period"], cur))
    return pts


def _pick_scissors(data, period, ptype):
    m1, m2 = data.get("m1_yoy"), data.get("m2_yoy")
    return None if m1 is None or m2 is None else round(float(m1) - float(m2), 2)


def _pick_monthly(ytd, mom):
    """🔴 判的是 `monthly_average` 的**第二个返回值 ok**，不是 `v is None`。
    该函数缺值时返回 `(0, False)`——只判 v 会把「这期没数据」画成 0，
    在折线上造出一个假的谷底，而读者无从分辨它和「这期真的是 0」。"""
    def inner(data, period, ptype):
        v, ok = monthly_average(data, ytd, mom, period, ptype)
        return round(v, 2) if ok else None
    return inner


def render_trend_scissors(contract, history):
    pts = _trend_points(contract, history, _pick_scissors)
    if not pts:
        return "> 剪刀差趋势：侧车与本期都取不到 `m1_yoy` / `m2_yoy`，不画。\n"
    sig = contract["thresholds"]["signals"]
    md = _xychart("M1−M2 剪刀差 · %s 序列" % contract["period_type"],
                  [p for p, _ in pts], [v for _, v in pts], "pct")
    return md + ("> 共 %d 期（侧车同类型历史 + 本期）。活化线 %s / 沉淀线 %s。"
                 "x 轴按侧车实际期次排列，**缺期不补**——轴上没有的期次即未入权威表。\n"
                 % (len(pts), fmt(sig["scissors_active"]), fmt(sig["scissors_sink"])))


def render_trend_household(contract, history, ytd, mom, label, warm):
    """🔴 拆成单线图而不是双线：`xychart-beta` **没有图例**，两条线画在一张图上
    无法分辨哪条是哪条。宁可两张图，也不要一张看不懂的。"""
    pts = _trend_points(contract, history, _pick_monthly(ytd, mom))
    if not pts:
        return "> %s 趋势：取不到数据，不画。\n" % label
    md = _xychart("%s 月均 · %s 序列" % (label, contract["period_type"]),
                  [p for p, _ in pts], [v for _, v in pts], "亿元")
    return md + "> 共 %d 期。暖身线 %s 亿元。月均口径：`_mom` 优先，否则 `_ytd` ÷ 期内月数。\n" % (
        len(pts), fmt(warm))


TSF_ITEMS = [
    ("对实体人民币贷款", "tsf_flow_rmb_loan_ytd", "tsf_flow_rmb_loan_mom"),
    ("政府债券", "tsf_flow_govt_bond_ytd", "tsf_flow_govt_bond_mom"),
    ("企业债券", "tsf_flow_corp_bond_ytd", "tsf_flow_corp_bond_mom"),
    ("股票融资", "tsf_flow_equity_ytd", "tsf_flow_equity_mom"),
    ("外币贷款", "tsf_flow_fx_loan_ytd", "tsf_flow_fx_loan_mom"),
    ("委托贷款", "tsf_flow_entrust_ytd", "tsf_flow_entrust_mom"),
    ("信托贷款", "tsf_flow_trust_ytd", "tsf_flow_trust_mom"),
    ("未贴现承兑汇票", "tsf_flow_bankaccept_ytd", "tsf_flow_bankaccept_mom"),
]


def render_tsf_structure(contract):
    """社融增量结构占比。分母是社融增量总量，分子逐项同口径取。

    ⚠️ 本段**只输出占比这一种百分数**：叙述里引用的「政府债占 30.9%」必须与这里
    算出来的是同一个数，两处各算各的迟早会对不上。"""
    d = contract["data"]
    total, _ = _pick(d, "tsf_flow_ytd", "tsf_flow_mom")
    if not total:
        return "> 社融增量结构：取不到 `tsf_flow_ytd` / `tsf_flow_mom`，不画。\n"
    rows = []
    for label, ytd, mom in TSF_ITEMS:
        v, _ = _pick(d, ytd, mom)
        if v is None:
            continue
        rows.append((label, v, float(v) / float(total)))
    if not rows:
        return "> 社融增量结构：本期无分项数据，不画。\n"
    rows.sort(key=lambda r: r[2], reverse=True)
    lines = ["", "```"]
    for label, v, share in rows:
        lines.append("%s%s 亿元  %s  %5.1f%%" % (
            pad(label, 18), "%9s" % fmt(v), bar(share), share * 100))
    lines.append("```")
    lines.append("")
    lines.append("> 分母为社融增量总量 %s 亿元。负值项（净偿还）条留空。" % fmt(total))
    lines.append("")
    return "\n".join(lines)


# ── 组装 ─────────────────────────────────────────────────────────────────────

TITLE_SUFFIX = {"monthly": "金融统计数据解读", "q1": "一季度金融统计数据解读",
                "h1": "上半年金融统计数据解读", "q1_q3": "前三季度金融统计数据解读",
                "annual": "全年金融统计数据解读"}


def build_note(contract, history, now, existing_md=""):
    sig = contract["thresholds"]["signals"]
    derived = evaluate(contract["data"], contract["period"], contract["period_type"], sig)

    out = ["---"]
    for k, v in build_frontmatter(contract, derived, now):
        out.append("%s: %s" % (k, v))
    out.append("---")
    out.append("")

    period, ptype = contract["period"], contract["period_type"]
    if ptype == "monthly":
        out.append("# %s 年 %d 月%s" % (period[:4], int(period[5:]), TITLE_SUFFIX["monthly"]))
    else:
        out.append("# %s 年%s" % (period[:4], TITLE_SUFFIX[ptype]))
    out.append("")
    if contract.get("is_revision") and contract.get("supersedes_published_at"):
        out.append("> 本文取代 %s 版本。" % contract["supersedes_published_at"])
        out.append("")

    out.append(BEGIN)
    body = []
    body.append(with_check("## 本期数据\n\n" + render_table_current(contract, history) + "\n"))
    body.append(with_check("## 前 12 期\n\n" + render_table_history(history, ptype) + "\n"))

    body.append("## 信号\n\n活化 %s · 楼市 %s · 消费 %s · 信贷 %s · 温度 %d/%d\n" % (
        EMOJI[derived["activation"]], EMOJI[derived["housing"]],
        EMOJI[derived["consumption"]], EMOJI[derived["credit"]],
        derived["score"], derived["known"]))
    body.append(render_signal_bars(derived, sig) + "\n")

    body.append("## 趋势\n\n")
    body.append(render_trend_scissors(contract, history) + "\n")
    body.append(render_trend_household(contract, history, "loan_hh_mlt_ytd", "loan_hh_mlt_mom",
                                       "住户中长期贷款", sig["hh_mlt_monthly_warm"]) + "\n")
    body.append(render_trend_household(contract, history, "loan_hh_short_ytd", "loan_hh_short_mom",
                                       "住户短期贷款", sig["hh_short_monthly_warm"]) + "\n")

    body.append("## 社融增量结构\n")
    body.append(render_tsf_structure(contract) + "\n")
    body.append(NARR_OPEN + "\n" + reading_hints(contract, derived) + NARR_CLOSE + "\n")
    out.append("".join(body).rstrip("\n"))

    md_so_far = "\n".join(out) + "\n"
    out.append("<!-- seal: %s -->" % seal_digest(md_so_far + "<!-- seal: "))
    out.append(END)
    out.append("")
    out.append(ANNOTATION_HEADING)
    annotations = extract_annotations(existing_md)
    out.append(annotations.rstrip("\n") if annotations.strip() else "（手写区，永不被覆盖）")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="契约 + 侧车 → 笔记（M3 的 TASK-005）")
    ap.add_argument("contract")
    ap.add_argument("history", nargs="?")
    ap.add_argument("--existing")
    # 🔴 缺省取当天，不是空串（M3 的 TASK-005 订正）：SKILL.md Step 3 的调用行**不传 `--now`**，
    # 而 `created` / `updated` 是 note-format.md 列的 vault 必填字段 —— 缺省为空会产出
    # 必需字段为空的笔记，且**静默**。取当天则「某个测试忘传 --now」会让 golden 逐字节比对
    # 当场变红，是**响的**失败。两种失败模式不对称，故选前者。
    ap.add_argument("--now", default=datetime.date.today().isoformat())
    ap.add_argument("--print-name", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.contract, encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, ValueError) as err:
        sys.stderr.write("contract 读取或解析失败: %s\n" % err)
        return 2

    if args.print_name:
        sys.stdout.write(note_name(contract["period"], contract["period_type"]) + "\n")
        return 0

    if not args.history:
        sys.stderr.write("history 侧车路径缺失\n")
        return 2
    try:
        with open(args.history, encoding="utf-8") as fh:
            history = json.load(fh)
    except (OSError, ValueError) as err:
        sys.stderr.write("history 侧车读取或解析失败: %s\n" % err)
        return 2

    ok, msg = assert_pair(contract, history)
    if not ok:
        sys.stderr.write(msg + "\n")
        return 2

    existing_md = ""
    if args.existing:
        try:
            with open(args.existing, encoding="utf-8") as fh:
                existing_md = fh.read()
        except OSError as err:
            sys.stderr.write("--existing 读取失败: %s\n" % err)
            return 2

    sys.stdout.write(build_note(contract, history, args.now, existing_md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
