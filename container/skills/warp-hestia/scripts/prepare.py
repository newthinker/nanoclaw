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
import hashlib
import json
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

    body.append("## 信号\n\n活化 %s · 楼市 %s · 消费 %s · 信贷 %s · 温度 %d/%d\n\n" % (
        EMOJI[derived["activation"]], EMOJI[derived["housing"]],
        EMOJI[derived["consumption"]], EMOJI[derived["credit"]],
        derived["score"], derived["known"]))
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
    ap.add_argument("--now", default="")
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
