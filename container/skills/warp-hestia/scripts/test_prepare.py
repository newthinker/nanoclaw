#!/usr/bin/env python3
"""prepare.py 的 unittest。M3 的 TASK-005。只用标准库。

done_criteria → 测试映射（写在这里是防护性写入，验证者逐条对照用）：
  functional[0] 夹具            → FixturesShape
  functional[1] 模块结构/接口    → ModuleInterface, PrintName
  functional[2] frontmatter 全表 → Frontmatter（14 基础 + 9 派生 + 4 信号 + bill_ratio 同口径 + 判读提示）
  functional[3] 两张表 + 两级校验 → Tables, CheckLines
  functional[4] 三期 golden      → Golden.test_three_periods
                golden 逐字节    → Golden.test_golden_files_byte_exact
                确定性           → Golden.test_deterministic
                派生分支全覆盖    → Derived
  boundary B1/B2/B6/O3/批注+标记 → Boundary
  error_handling                → BadInput
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
GOLDEN = os.path.join(FIX, "golden")
PREP = os.path.join(HERE, "prepare.py")

sys.path.insert(0, HERE)

import prepare as P  # noqa: E402  —— 必须在 sys.path 插入之后


def run(args, check=True):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, check=check)


def prepare(name, extra=()):
    return run([PREP, f"{FIX}/{name}.json", f"{FIX}/{name}.history.json",
                "--now", "2026-09-12", *extra]).stdout


def fm(md):
    """取 frontmatter 为 dict。值保持字符串原样，断言时按字符串比。"""
    body = md.split("---\n", 2)[1]
    return dict(l.split(": ", 1) for l in body.splitlines() if ": " in l)


def load_fixture(name):
    with open(f"{FIX}/{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_history(name):
    with open(f"{FIX}/{name}.history.json", encoding="utf-8") as fh:
        return json.load(fh)


def section(md, title):
    """取 `## <title>` 标题之后、本段 check 行之前的正文。"""
    return md.split(f"## {title}\n", 1)[1].split("<!-- check:", 1)[0]


def header_cells(md, title):
    """该段第一张表的表头行，拆成去空白的单元格列表。"""
    header = [l for l in section(md, title).splitlines() if l.startswith("|")][0]
    return [c.strip() for c in header.strip("|").split("|")]


class FixturesShape(unittest.TestCase):
    """functional[0]：夹具齐全。不写死总数（修订契约与其侧车另计），只钉五期必须在。"""

    FIVE = ["2020-06-h1", "2025-12-annual", "2026-06-h1", "2023-08-monthly", "2022-07-monthly"]

    def test_five_periods_and_sidecars(self):
        for n in self.FIVE:
            with self.subTest(n):
                self.assertTrue(os.path.isfile(f"{FIX}/{n}.json"), f"缺契约 {n}")
                self.assertTrue(os.path.isfile(f"{FIX}/{n}.history.json"), f"缺侧车 {n}")

    def test_sidecar_shape(self):
        h = load_history("2026-06-h1")
        self.assertEqual(h["for"], "2026-06-h1")
        self.assertIn("same_type", h)
        self.assertIn("monthly_recent", h)
        # 每项是 {meta:{...}, data:{...}}，不是扁平结构
        self.assertIn("meta", h["same_type"][0])
        self.assertIn("period", h["same_type"][0]["meta"])

    def test_revision_fixture(self):
        c = load_fixture("2025-12-annual-rev")
        self.assertTrue(c["is_revision"])
        self.assertEqual(c["supersedes_published_at"], "2026-01-15")
        self.assertEqual(c["published_at"], "2026-02-20")

    def test_existing_note_has_two_annotation_lines(self):
        with open(f"{FIX}/existing-2026-06-h1.md", encoding="utf-8") as fh:
            body = fh.read()
        tail = body.split("## 我的批注", 1)[1]
        self.assertIn("这是我手写的第一行批注", tail)
        self.assertIn("第二行批注", tail)


class ModuleInterface(unittest.TestCase):
    """functional[1]：模块结构与「只用标准库」。"""

    REQUIRED = ["months_in_period", "monthly_average", "same_caliber_pair", "evaluate",
                "note_name", "build_frontmatter", "render_table_current", "render_table_history",
                "with_check", "extract_annotations", "main"]

    def test_functions_exist(self):
        for name in self.REQUIRED:
            with self.subTest(name):
                self.assertTrue(callable(getattr(P, name, None)), f"缺函数 {name}")

    def test_stdlib_only(self):
        allowed = {"json", "hashlib", "argparse", "datetime", "re", "os", "sys", "math",
                   "unicodedata"}
        with open(PREP, encoding="utf-8") as fh:
            src = fh.read()
        mods = set()
        for line in src.splitlines():
            m = re.match(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)", line)
            if m:
                mods.add(m.group(1).split(".")[0])
        self.assertEqual(mods - allowed, set(), f"引入了标准库之外的模块: {mods - allowed}")


class PrintName(unittest.TestCase):
    """functional[1]：--print-name 取无月份版（M3 的 TASK-005 的 G6b 裁决）。"""

    def test_h1_has_no_month(self):
        out = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2026-06-h1.history.json",
                   "--print-name"]).stdout.strip()
        self.assertEqual(out, "2026 上半年金融数据解读.md")

    def test_all_five_period_types(self):
        cases = [("2026-08", "monthly", "2026-08 金融数据解读.md"),
                 ("2026-03", "q1", "2026 一季度金融数据解读.md"),
                 ("2026-06", "h1", "2026 上半年金融数据解读.md"),
                 ("2026-09", "q1_q3", "2026 前三季度金融数据解读.md"),
                 ("2026-12", "annual", "2026 全年金融数据解读.md")]
        for period, ptype, want in cases:
            with self.subTest(ptype):
                self.assertEqual(P.note_name(period, ptype), want)


class Golden(unittest.TestCase):
    """functional[4]①②③"""

    def test_three_periods(self):
        for name, score in [("2020-06-h1", "2"), ("2025-12-annual", "0"), ("2026-06-h1", "1")]:
            with self.subTest(name):
                f = fm(prepare(name))
                self.assertEqual(f["temp_score"], score)
                self.assertEqual(f["temp_known"], "4")

    def test_golden_files_byte_exact(self):
        """🔴 与入库的期望文件逐字节比对——自比（determinism）不能替代这一条：
        输出乱序的表、错的表头、少一列，只要两次一样，自比就全绿。"""
        for name in ["2026-06-h1", "2023-08-monthly"]:
            with self.subTest(name):
                path = os.path.join(GOLDEN, f"{name}.md")
                self.assertTrue(os.path.isfile(path), f"缺 golden 期望文件 {path}")
                with open(path, encoding="utf-8") as fh:
                    want = fh.read()
                self.assertEqual(prepare(name), want, f"{name} 输出与期望文件不一致")

    def test_deterministic(self):
        for name in ["2026-06-h1", "2023-08-monthly"]:
            with self.subTest(name):
                self.assertEqual(prepare(name), prepare(name))


class Derived(unittest.TestCase):
    """functional[4]④⑤：五条派生分支全覆盖（_mom / ÷MM / ÷3 / ÷6 / ÷9 / ÷12）。"""

    def test_mom_preferred_2023_08(self):
        self.assertEqual(fm(prepare("2023-08-monthly"))["hh_mlt_monthly"], "1602")

    def test_mom_preferred_2022_07(self):
        # 需求自标的订正：该期贷款分部门是 _mom（1486），走的**不是** _ytd ÷ MM
        self.assertEqual(fm(prepare("2022-07-monthly"))["hh_mlt_monthly"], "1486")

    def test_ytd_divided_by_month_number(self):
        """真正走 `_ytd ÷ MM` 的样本夹具里没有，用内联最小契约走函数级接口。"""
        got, ok = P.monthly_average({"loan_hh_mlt_ytd": 7000},
                                    "loan_hh_mlt_ytd", "loan_hh_mlt_mom", "2022-07", "monthly")
        self.assertTrue(ok)
        self.assertEqual(got, 1000)

    def test_divided_by_six(self):
        f = fm(prepare("2026-06-h1"))
        self.assertEqual(f["hh_mlt_monthly"], "368.67")   # 2212/6
        self.assertEqual(f["signal_housing"], "red")
        self.assertEqual(f["signal_credit"], "green")     # 7.32%

    def test_divided_by_twelve(self):
        c = load_fixture("2025-12-annual")
        want = round(c["data"]["loan_hh_mlt_ytd"] / 12, 2)
        f = fm(prepare("2025-12-annual"))
        self.assertEqual(float(f["hh_mlt_monthly"]), want)

    def test_divided_by_three_and_nine(self):
        for ptype, divisor in [("q1", 3), ("q1_q3", 9)]:
            with self.subTest(ptype):
                got, ok = P.monthly_average({"loan_hh_mlt_ytd": 9000},
                                            "loan_hh_mlt_ytd", "loan_hh_mlt_mom", "2026-03", ptype)
                self.assertTrue(ok)
                self.assertEqual(got, 9000 / divisor)

    def test_mom_beats_ytd_when_both_present(self):
        """🔴 变异逼出来的缺口：夹具里每个字段只有 `_mom` 或 `_ytd` 之一，
        所以「`_mom` 优先」这条语义在夹具上**行使不到**——把顺序反过来的变异存活了。
        这里构造两者都在的输入，钉住优先级。"""
        got, ok = P.monthly_average({"loan_hh_mlt_ytd": 12000, "loan_hh_mlt_mom": 1500},
                                    "loan_hh_mlt_ytd", "loan_hh_mlt_mom", "2026-06", "h1")
        self.assertTrue(ok)
        self.assertEqual(got, 1500, "_mom 非空时就是它，不除以月数")

    def test_pick_prefers_mom_when_both_present(self):
        """表格取值同序：`_mom` 优先，且要如实报出取的是哪个口径。"""
        v, mark = P._pick({"loan_bill_ytd": 8143, "loan_bill_mom": 3472},
                          "loan_bill_ytd", "loan_bill_mom")
        self.assertEqual(v, 3472)
        self.assertEqual(mark, "_mom")

    def test_same_caliber_pair_prefers_mom_when_both_present(self):
        bill, total, ok = P.same_caliber_pair(
            {"loan_bill_ytd": 8143, "loan_bill_mom": 3472,
             "loan_corp_total_ytd": 111300, "loan_corp_total_mom": 9488},
            "loan_bill_ytd", "loan_bill_mom", "loan_corp_total_ytd", "loan_corp_total_mom")
        self.assertTrue(ok)
        self.assertEqual((bill, total), (3472, 9488), "两侧都取 _mom")

    def test_scissors(self):
        self.assertEqual(fm(prepare("2026-06-h1"))["scissors"], "-4")


class Frontmatter(unittest.TestCase):
    """functional[2]：spec §6.1 全表——14 基础 + 9 派生 + 4 信号。"""

    BASE = ["type", "domain", "created", "updated", "tags", "sources", "period", "period_type",
            "published_at", "caliber_version", "extractor", "source_url",
            "generated_by", "contract_generated_by"]
    DERIVED = ["m2_yoy", "m1_yoy", "scissors", "tsf_stock_yoy", "hh_mlt_monthly",
               "hh_short_monthly", "bill_ratio", "temp_score", "temp_known"]
    SIGNALS = ["signal_activation", "signal_housing", "signal_consumption", "signal_credit"]

    def setUp(self):
        self.md = prepare("2026-06-h1")
        self.f = fm(self.md)

    def test_base_keys(self):
        for k in self.BASE:
            with self.subTest(k):
                self.assertIn(k, self.f)

    def test_derived_keys(self):
        for k in self.DERIVED:
            with self.subTest(k):
                self.assertIn(k, self.f)

    def test_signal_keys(self):
        for k in self.SIGNALS:
            with self.subTest(k):
                self.assertIn(k, self.f)
                self.assertIn(self.f[k], ("green", "yellow", "red", "unknown"))

    def test_created_updated_nonempty_without_now_flag(self):
        """🔴 验证者在 M3 的 TASK-005 的 prepare 部分验收时发现：`--now` 缺省为空串，而 SKILL.md Step 3 **不传它**
        ⇒ 实产笔记的 `created` / `updated` 两个都是空值。原有断言只查**键存在**（14 个键确实都在）
        ⇒ 「键存在但值为空」这个形态**恒真、零覆盖**。这里断言非空且等于当天。"""
        import datetime
        out = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2026-06-h1.history.json"]).stdout
        f = fm(out)
        today = datetime.date.today().isoformat()
        self.assertEqual(f["created"], today)
        self.assertEqual(f["updated"], today)

    def test_explicit_now_still_wins(self):
        """显式传 `--now` 时仍以它为准（golden 就是靠这个稳定的）。"""
        self.assertEqual(self.f["created"], "2026-09-12")
        self.assertEqual(self.f["updated"], "2026-09-12")

    def test_no_reviewed_no_source(self):
        self.assertNotIn("reviewed", self.f)
        self.assertNotIn("source", self.f)

    def test_generated_by_values(self):
        self.assertEqual(self.f["generated_by"], "warp-hestia@v1")
        self.assertEqual(self.f["contract_generated_by"], "contract@v1/replay")

    def test_bill_ratio_same_caliber(self):
        """spec §5.3：票据 ÷ 企业贷款合计 × 100，分子分母**同口径**。"""
        c = load_fixture("2026-06-h1")
        bill, total, ok = P.same_caliber_pair(c["data"], "loan_bill_ytd", "loan_bill_mom",
                                              "loan_corp_total_ytd", "loan_corp_total_mom")
        self.assertTrue(ok)
        self.assertEqual(float(self.f["bill_ratio"]), round(bill / total * 100, 2))
        self.assertEqual(self.f["bill_ratio"], "7.32")

    def test_bill_ratio_rejects_cross_caliber(self):
        """🔴 变异测试逼出来的缺口：原来只用 2026-06-h1 断言，而它两个字段都是 `_ytd`，
        「允许跨口径配对」这个变异**存活**了。这里构造只有一侧是 `_mom` 的输入：
        正确行为是**回落到 (_ytd, _ytd)**，都取不到就 ok=False，**绝不拿 _mom 配 _ytd**。"""
        # 分子有 _mom、分母只有 _ytd ⇒ 无同口径对 ⇒ ok=False
        _, _, ok = P.same_caliber_pair({"loan_bill_mom": 3472, "loan_corp_total_ytd": 111300},
                                       "loan_bill_ytd", "loan_bill_mom",
                                       "loan_corp_total_ytd", "loan_corp_total_mom")
        self.assertFalse(ok, "不得把 _mom 与 _ytd 配成一对")
        # 反方向同样
        _, _, ok = P.same_caliber_pair({"loan_bill_ytd": 8143, "loan_corp_total_mom": 9488},
                                       "loan_bill_ytd", "loan_bill_mom",
                                       "loan_corp_total_ytd", "loan_corp_total_mom")
        self.assertFalse(ok, "反方向也不得跨口径配对")
        # 无同口径对 ⇒ 信贷信号 unknown（不是红也不是绿）
        sig = load_fixture("2026-06-h1")["thresholds"]["signals"]
        d = P.evaluate({"m1_yoy": 4.0, "m2_yoy": 8.0,
                        "loan_bill_mom": 3472, "loan_corp_total_ytd": 111300},
                       "2026-06", "h1", sig)
        self.assertEqual(d["credit"], "unknown")

    def test_bill_ratio_total_zero_is_unknown(self):
        """企业贷款合计为 0 ⇒ 比值无定义 ⇒ unknown（不是红也不是绿）。"""
        sig = load_fixture("2026-06-h1")["thresholds"]["signals"]
        d = P.evaluate({"m1_yoy": 4.0, "m2_yoy": 8.0,
                        "loan_bill_ytd": 100, "loan_corp_total_ytd": 0}, "2026-06", "h1", sig)
        self.assertEqual(d["credit"], "unknown")

    def test_narrative_has_reading_hints(self):
        """reviewer O4：narrative 段内必须含 prepare.py 生成的判读提示，不是空段。"""
        seg = self.md.split("<!-- narrative -->", 1)[1].split("<!-- /narrative -->", 1)[0]
        self.assertGreater(len(seg.strip()), 0, "narrative 段是空的")
        self.assertIn("八问", seg)


class PairingGuard(unittest.TestCase):
    """F2（M3 的 TASK-005 返工）：契约与侧车的**配对**必须被校验。

    🔴 缺陷形态：`prepare.py` 从 history 上只读 `same_type`，侧车顶层的 `for` 字段
    （atlas `history.go` 写出，值形如 `2026-06-h1`）**被读 0 次** ⇒ 错配的一对喂进去，
    prepare 与 verify **双双 exit 0**，而 frontmatter/标题/四信号/温度全对（都来自契约）、
    **两张表全错**（都来自侧车）——笔记自洽地看起来完全正常。
    这是这条链路上**唯一能机器判定「这两个文件是一对」的事实**。"""

    def test_mismatched_pair_exits_2(self):
        r = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2025-12-annual.history.json",
                 "--now", "2026-09-12"], check=False)
        self.assertEqual(r.returncode, 2, "错配的契约×侧车必须被拒绝")
        err = r.stderr
        self.assertIn("2026-06-h1", err, "报错要打印契约侧的期望值")
        self.assertIn("2025-12-annual", err, "报错要打印侧车实际的 for")
        self.assertEqual(r.stdout, "", "被拒绝时不得产出半份笔记")

    def test_matched_pairs_unaffected(self):
        """正配的五期一条都不能变红。"""
        for name in ["2020-06-h1", "2025-12-annual", "2026-06-h1",
                     "2023-08-monthly", "2022-07-monthly"]:
            with self.subTest(name):
                r = run([PREP, f"{FIX}/{name}.json", f"{FIX}/{name}.history.json",
                         "--now", "2026-09-12"], check=False)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_revision_fixture_pairs_by_period_not_filename(self):
        """🔴 判据是 `for == period + "-" + period_type`，**不是文件名**：
        修订夹具叫 `2025-12-annual-rev.*` 而它的 `for` 是 `2025-12-annual`——
        若拿文件名做判据，这一对会被误拒。"""
        with open(f"{FIX}/2025-12-annual-rev.history.json", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["for"], "2025-12-annual")
        r = run([PREP, f"{FIX}/2025-12-annual-rev.json",
                 f"{FIX}/2025-12-annual-rev.history.json", "--now", "2026-09-12"], check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sidecar_for_field_is_actually_read(self):
        """钉住「`for` 被读到了」这件事本身——缺陷正是它命中 0 次。"""
        import prepare as P
        self.assertTrue(hasattr(P, "assert_pair"), "缺少配对校验函数 assert_pair")


class ExistingGuard(unittest.TestCase):
    """F1（M3 的 TASK-005 返工）：`--existing` 指向**不存在**的文件时的契约。

    ⚠️ 现有三处 `--existing` 用例**全部指向存在的文件**，所以这个洞从未被行使——
    与「一条判据被更早的判据遮蔽」同族：**测试用例的取值分布让某条路径永不发生**。
    这条测试钉住 prepare.py 的契约，从而让 SKILL.md 那侧的 `[ -f ]` 守卫成为**必需**。"""

    def test_existing_nonexistent_exits_2(self):
        r = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2026-06-h1.history.json",
                 "--now", "2026-09-12", "--existing", "/nonexistent/note.md"], check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("existing", r.stderr)
        self.assertEqual(r.stdout, "", "失败时不得产出半份笔记（实测 0 字节）")

    def test_create_scenario_without_existing_works(self):
        """create 场景（笔记尚不存在）：**不传** --existing ⇒ 正常产出。
        这正是 SKILL.md 修好后该走的路径。"""
        r = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2026-06-h1.history.json",
                 "--now", "2026-09-12"], check=False)
        self.assertEqual(r.returncode, 0)
        self.assertGreater(len(r.stdout), 0)
        self.assertIn("（手写区，永不被覆盖）", r.stdout, "create 场景批注区是占位文本")

    def test_update_scenario_with_existing_works(self):
        """update 场景（笔记已存在）：传 --existing ⇒ 批注区被保留。"""
        r = run([PREP, f"{FIX}/2026-06-h1.json", f"{FIX}/2026-06-h1.history.json",
                 "--now", "2026-09-12", "--existing", f"{FIX}/existing-2026-06-h1.md"],
                check=False)
        self.assertEqual(r.returncode, 0)
        self.assertIn("这是我手写的第一行批注", r.stdout)


class Tables(unittest.TestCase):
    """functional[3]：两张表的结构义务。"""

    def setUp(self):
        self.md = prepare("2026-06-h1")

    def test_current_table_three_value_columns(self):
        """五列：指标 / 单位 / 本期 / 上期 / 去年同期。三个值列的表头**以对应标签开头**
        （后面还带期次与口径标注，故不能做等值比较）。"""
        cells = header_cells(self.md, "本期数据")
        self.assertEqual(len(cells), 5, "表头列数")
        self.assertEqual(cells[0], "指标")
        self.assertEqual(cells[1], "单位")
        for cell, label in zip(cells[2:], ["本期", "上期", "去年同期"]):
            with self.subTest(label):
                self.assertTrue(cell.startswith(label), f"列头 {cell!r} 应以 {label!r} 开头")

    def test_current_table_has_caliber_annotation(self):
        """口径标注是 glossary『跨口径对比禁忌』与 spec §9 风险表的落地载体。
        🔴 只断言「出现了口径字样」太弱——表头恒含「本期 …（口径 X）」，去掉 ⚠️ 标注也照过
        （变异 M14 实测只被 golden 逐字节比对杀死，本条没响）。故改为：**当对比列的口径
        与本期不同时，该列表头必须带 ⚠️ 标注**。"""
        sec = section(self.md, "本期数据")
        self.assertIn("口径", sec)
        self.assertRegex(sec, r"20(15|23|25)-01")

    def test_caliber_mark_fires_when_calibers_differ(self):
        h = load_history("2023-08-monthly")
        cur = load_fixture("2023-08-monthly")["caliber_version"]
        series = sorted(h["same_type"], key=lambda e: e["meta"]["period"], reverse=True)
        ya = next(e for e in series if e["meta"]["period"] == "2022-08")
        self.assertNotEqual(ya["meta"]["caliber_version"], cur, "夹具前提：去年同期口径确实不同")

        ya_cell = header_cells(prepare("2023-08-monthly"), "本期数据")[4]
        self.assertIn("⚠️", ya_cell, f"口径不同的列必须带 ⚠️ 标注，实际: {ya_cell!r}")
        self.assertIn(ya["meta"]["caliber_version"], ya_cell)

    def test_caliber_mark_absent_when_calibers_match(self):
        """反方向：口径相同的列**不该**有 ⚠️，否则标注就成了噪声。"""
        cells = header_cells(prepare("2026-06-h1"), "本期数据")
        self.assertNotIn("⚠️", "".join(cells))   # ⚠️ 只可能出现在单元格内容里

    def test_current_table_comparison_columns_come_from_same_type(self):
        """🔴 F2 的污染面**不止**「前 12 期」表：`render_table_current` 的上期/去年同期
        两列同样取自侧车 `same_type`（`series[0]` 就是上期）⇒ 错配时**本期数据表的对比列
        也错**，而那是解读的起点。这条把「对比列的来源」钉死。"""
        h = load_history("2026-06-h1")
        series = sorted(h["same_type"], key=lambda e: e["meta"]["period"], reverse=True)
        cells = header_cells(self.md, "本期数据")
        self.assertTrue(cells[3].startswith("上期 " + series[0]["meta"]["period"]),
                        f"上期列必须取自 same_type 的最新一期，实际: {cells[3]!r}")

    def test_history_table_rows_come_from_sidecar_same_type(self):
        h = load_history("2026-06-h1")
        want_periods = [e["meta"]["period"] for e in h["same_type"]]
        sec = section(self.md, "前 12 期")
        rows = [l for l in sec.splitlines() if l.startswith("|")]
        body = rows[2:]                       # 去掉表头与分隔行
        self.assertEqual(len(body), len(want_periods),
                         "前 12 期表的行数必须等于侧车 same_type 的条数，不补齐不截断")
        for p in want_periods:
            with self.subTest(p):
                self.assertIn(p, sec)

    def test_history_table_uses_same_type_even_for_monthly(self):
        """🔴 monthly 契约的侧车**没有** monthly_recent（Atlas 侧 omitzero），
        前 12 期表必须仍走 same_type——写成 monthly_recent 会得到 0 行而不报错。"""
        h = load_history("2023-08-monthly")
        self.assertEqual(len(h.get("monthly_recent") or []), 0, "夹具前提：monthly 侧车无 monthly_recent")
        self.assertEqual(len(h["same_type"]), 12)
        sec = section(prepare("2023-08-monthly"), "前 12 期")
        rows = [l for l in sec.splitlines() if l.startswith("|")]
        self.assertEqual(len(rows[2:]), 12, "monthly 的前 12 期表应有 12 行")
        for e in h["same_type"]:
            with self.subTest(e["meta"]["period"]):
                self.assertIn(e["meta"]["period"], sec)


class CheckLines(unittest.TestCase):
    """functional[3]：两级校验——分段 check 恰 2 条 + 封条 seal 恰 1 条。条数写死，不从 `## ` 推。"""

    def setUp(self):
        self.md = prepare("2026-06-h1")

    def test_exactly_two_check_lines(self):
        self.assertEqual(self.md.count("<!-- check: "), 2)

    def test_exactly_one_seal_line(self):
        self.assertEqual(self.md.count("<!-- seal: "), 1)

    def test_signal_section_has_no_check(self):
        seg = self.md.split("## 信号\n", 1)[1].split("<!-- narrative -->", 1)[0]
        self.assertNotIn("<!-- check:", seg)

    def test_heading_count_differs_from_check_count(self):
        """钉住『不能按 `## ` 标题数推 check 行数』：机器区 6 个 `## ` 而 check 恒 2。

        🔴 2026-09-16 加图表段后由 3 变 5（`## 信号` / `## 趋势` / `## 社融增量结构` 都不发
        check 行）；2026-09-18 加 `## 同比变化` 后变 6，check 仍是 2。
        **这条测试的价值恰恰在于它会随结构变化而红**——它逼着人重新确认
        「check 行数不从结构推」这件事仍然成立，而不是让两个数悄悄一起漂。"""
        mz = self.md.split("<!-- machine-generated: begin -->", 1)[1] \
                    .split("<!-- machine-generated: end -->", 1)[0]
        self.assertEqual(len([l for l in mz.splitlines() if l.startswith("## ")]), 6)
        self.assertEqual(self.md.count("<!-- check: "), 2)

    def test_check_covers_from_previous_heading(self):
        """作用域：从上一个 `## ` 标题行起到本 check 行之前。"""
        for title in ["本期数据", "前 12 期"]:
            with self.subTest(title):
                seg = self.md.split(f"## {title}\n", 1)[1]
                body, rest = seg.split("<!-- check: ", 1)
                got = rest.split(" -->", 1)[0]
                covered = f"## {title}\n" + body
                self.assertEqual(hashlib.sha256(covered.encode("utf-8")).hexdigest(), got)

    def test_seal_excludes_narrative(self):
        """封条覆盖 begin 的下一行 → seal 行之前，**扣除** narrative 块（含两行标记）。"""
        seal = seal_of(self.md)
        self.assertEqual(P.seal_digest(self.md), seal)
        # 改 narrative 不影响封条
        edited = self.md.replace("<!-- narrative -->",
                                 "<!-- narrative -->\n模型写的叙述，甚至带 ## 小标题。", 1)
        self.assertEqual(P.seal_digest(edited), seal)

    def test_seal_catches_deleted_check_line(self):
        """封条是删除类篡改的唯一防线：删掉一条 check 行，分段校验没了不比对，封条必须变。"""
        line = [l for l in self.md.splitlines() if l.startswith("<!-- check: ")][0]
        edited = self.md.replace(line + "\n", "", 1)
        self.assertNotEqual(P.seal_digest(edited), seal_of(self.md))


def seal_of(md):
    return md.split("<!-- seal: ", 1)[1].split(" -->", 1)[0]


class Boundary(unittest.TestCase):
    """boundary 五条。"""

    def test_b1_months_in_period_parse_failure_returns_zero(self):
        for period, ptype in [("2026", "monthly"), ("2026-00", "monthly"),
                              ("2026-13", "monthly"), ("2026-06", "unknown_type")]:
            with self.subTest(f"{period}/{ptype}"):
                self.assertEqual(P.months_in_period(period, ptype), 0)

    def test_b1_zero_is_never_used_as_divisor(self):
        """0 是崩溃点：月数为 0 时 monthly_average 必须返回 ok=False，而不是除以 0。"""
        got, ok = P.monthly_average({"loan_hh_mlt_ytd": 7000},
                                    "loan_hh_mlt_ytd", "loan_hh_mlt_mom", "2026-13", "monthly")
        self.assertFalse(ok)
        self.assertEqual(got, 0)

    def test_b2_unknown_signal_makes_temp_known_less_than_four(self):
        """⚠️ 初稿所有断言都钉 temp_known == 4 ⇒『四信号有 unknown』零覆盖。"""
        sig = load_fixture("2026-06-h1")["thresholds"]["signals"]
        d = P.evaluate({"m1_yoy": 4.0, "m2_yoy": 8.0}, "2026-06", "h1", sig)
        self.assertEqual(d["housing"], "unknown")
        self.assertEqual(d["consumption"], "unknown")
        self.assertEqual(d["credit"], "unknown")
        self.assertLess(d["known"], 4)
        self.assertEqual(d["known"], 1)

    def test_signal_thresholds_at_exact_boundary(self):
        """🔴 变异逼出来的缺口：`>=` 改成 `>` 只在**恰好等于阈值**时有别，
        而没有夹具落在边界上（变异 M21 因此存活）。这里把四个信号的临界值逐个钉住。
        阈值取契约快照：scissors_active=0 / scissors_sink=-2 /
        hh_mlt_monthly_warm=2000 / hh_short_monthly_warm=0 /
        bill_ratio_healthy=10 / bill_ratio_severe=20。"""
        sig = load_fixture("2026-06-h1")["thresholds"]["signals"]

        def act(m1, m2):
            return P.evaluate({"m1_yoy": m1, "m2_yoy": m2}, "2026-06", "h1", sig)["activation"]

        self.assertEqual(act(8.0, 8.0), "green", "剪刀差恰为 scissors_active(0) ⇒ 绿（>=）")
        self.assertEqual(act(6.0, 8.0), "red", "剪刀差恰为 scissors_sink(-2) ⇒ 红（<=）")
        self.assertEqual(act(7.0, 8.0), "yellow", "介于两阈值之间 ⇒ 黄")

        def housing(mom):
            return P.evaluate({"loan_hh_mlt_mom": mom}, "2026-08", "monthly", sig)["housing"]

        self.assertEqual(housing(2000), "green", "月均恰为 warm(2000) ⇒ 绿（>=）")
        self.assertEqual(housing(1999.99), "red", "低于 warm 一点点 ⇒ 红，且**没有黄灯**")

        def consumption(mom):
            return P.evaluate({"loan_hh_short_mom": mom}, "2026-08", "monthly", sig)["consumption"]

        self.assertEqual(consumption(0), "green", "月均恰为 warm(0) ⇒ 绿")
        self.assertEqual(consumption(-0.01), "red")

        def credit(bill, total):
            return P.evaluate({"loan_bill_mom": bill, "loan_corp_total_mom": total},
                              "2026-08", "monthly", sig)["credit"]

        self.assertEqual(credit(9.99, 100), "green", "占比 < healthy(10) ⇒ 绿")
        self.assertEqual(credit(10, 100), "yellow", "占比恰为 healthy ⇒ 黄（绿是严格小于）")
        self.assertEqual(credit(19.99, 100), "yellow")
        self.assertEqual(credit(20, 100), "red", "占比恰为 severe(20) ⇒ 红（>=）")

    def test_b6_existing_without_annotation_heading(self):
        """spec §6.3：旧笔记无 `## 我的批注` ⇒ 视为空，不报错不吞内容。"""
        self.assertEqual(P.extract_annotations("# 标题\n正文，没有批注区。\n"), "")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write("# 旧笔记\n没有批注区。\n")
            path = fh.name
        try:
            md = prepare("2026-06-h1", ["--existing", path])
            self.assertIn("## 我的批注", md)
        finally:
            os.unlink(path)

    def test_o3_revision_path(self):
        """契约 is_revision ⇒ frontmatter 有 supersedes_published_at，标题下加一行。"""
        md = prepare("2025-12-annual-rev")
        f = fm(md)
        self.assertEqual(f["supersedes_published_at"], "2026-01-15")
        self.assertIn("本文取代 2026-01-15 版本", md)

    def test_non_revision_has_no_supersedes(self):
        f = fm(prepare("2026-06-h1"))
        self.assertNotIn("supersedes_published_at", f)

    def test_annotations_preserved_and_seven_markers(self):
        md = prepare("2026-06-h1", ["--existing", f"{FIX}/existing-2026-06-h1.md"])
        self.assertIn("这是我手写的第一行批注", md)
        self.assertIn("第二行批注", md)
        for m in ["<!-- machine-generated: begin -->", "<!-- narrative -->", "<!-- /narrative -->",
                  "<!-- machine-generated: end -->", "## 我的批注",
                  "<!-- check: ", "<!-- seal: "]:
            with self.subTest(m):
                self.assertIn(m, md)


class BadInput(unittest.TestCase):
    """error_handling：输入不合法 ⇒ 退出码非零 + stderr 有信息。"""

    def test_missing_history_exit_2(self):
        r = run([PREP, f"{FIX}/2026-06-h1.json", "/nonexistent.json"], check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("history", r.stderr)

    def test_bad_contract_json_nonzero(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{ this is not json")
            path = fh.name
        try:
            r = run([PREP, path, f"{FIX}/2026-06-h1.history.json"], check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue(r.stderr.strip())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()


# ── 图表（M3 后续：笔记加图，2026-09-16）──────────────────────────────────────

def chart_section(md, title):
    """取 `## <title>` 之后、到下一个 `## ` 或 narrative 开标记之前的正文。
    图表段不发 check 行（沿 `## 信号` 先例，靠封条保护），所以不能用 section()。"""
    body = md.split(f"## {title}\n", 1)[1]
    for stop in ("\n## ", P.NARR_OPEN):
        if stop in body:
            body = body.split(stop, 1)[0]
    return body


class Bar(unittest.TestCase):
    """条形渲染本身。"""

    def test_blocks_scale_with_ratio(self):
        self.assertEqual(P.bar(0.0, 10), "░░░░░░░░░░")
        self.assertEqual(P.bar(1.0, 10), "██████████")
        self.assertEqual(P.bar(0.18, 10), "██░░░░░░░░")

    def test_clamps_out_of_range(self):
        self.assertEqual(P.bar(-3, 10), "░░░░░░░░░░")
        self.assertEqual(P.bar(9.9, 10), "██████████")

    def test_none_is_empty_bar(self):
        self.assertEqual(P.bar(None, 10), "░░░░░░░░░░")


class SignalBars(unittest.TestCase):
    """四信号距绿灯多远——统一语义是「达成度」，绿灯即 100%。"""

    def rows(self, name="2026-06-h1"):
        md = prepare(name)
        return [l for l in chart_section(md, "信号").splitlines() if "│" in l or "达成" in l or "%" in l]

    def test_four_rows_one_per_signal(self):
        body = chart_section(prepare("2026-06-h1"), "信号")
        for label in ["活化", "楼市", "消费", "信贷"]:
            self.assertIn(label, body)
        self.assertIn("达成度", body)

    def test_housing_shows_ratio_to_warm_line(self):
        """368.67 / 2000 = 18%——红灯也要给出距离，而不是一律 0%。"""
        body = chart_section(prepare("2026-06-h1"), "信号")
        self.assertRegex(body, r"楼市.*368\.67.*18%")

    def test_green_signal_is_full(self):
        """信贷 7.32% < 健康线 10 ⇒ 绿灯 ⇒ 100%。"""
        body = chart_section(prepare("2026-06-h1"), "信号")
        self.assertRegex(body, r"信贷.*7\.32.*100%")

    def test_zero_threshold_signal_is_binary(self):
        """消费的暖身线是 0，达成与否非此即彼（该信号本就没有黄灯）。"""
        body = chart_section(prepare("2026-06-h1"), "信号")
        self.assertRegex(body, r"消费.*-980\.17.*0%")

    def test_achievement_helper_covers_all_four_shapes(self):
        sig = load_fixture("2026-06-h1")["thresholds"]["signals"]
        self.assertEqual(P.achievement("credit", 7.32, sig), 1.0)          # 绿灯
        self.assertEqual(P.achievement("credit", 25.0, sig), 0.0)          # 红灯
        self.assertAlmostEqual(P.achievement("credit", 15.0, sig), 0.5)    # 黄灯线性
        self.assertAlmostEqual(P.achievement("housing", 368.67, sig), 0.184335)
        self.assertEqual(P.achievement("consumption", -980.17, sig), 0.0)  # 阈值 0，二值
        self.assertEqual(P.achievement("consumption", 12.0, sig), 1.0)
        self.assertEqual(P.achievement("activation", -4.0, sig), 0.0)      # 低于沉淀线
        self.assertEqual(P.achievement("activation", 1.0, sig), 1.0)
        self.assertAlmostEqual(P.achievement("activation", -1.0, sig), 0.5)  # 两线之间
        self.assertIsNone(P.achievement("housing", None, sig))


class TrendCharts(unittest.TestCase):
    """mermaid 折线。Obsidian 1.12 内置 mermaid 支持 xychart-beta，无需插件。"""

    def test_trend_section_has_three_mermaid_blocks(self):
        body = chart_section(prepare("2026-06-h1"), "趋势")
        self.assertEqual(body.count("```mermaid"), 3)
        self.assertEqual(body.count("xychart-beta"), 3)

    def test_scissors_series_ends_with_current_period(self):
        """侧车只给「之前」的期次，本期必须由契约补在末尾，否则图上看不到当期。"""
        body = chart_section(prepare("2026-06-h1"), "趋势")
        block = body.split("```mermaid", 1)[1].split("```", 1)[0]
        self.assertRegex(block, r"x-axis \[.*2026-06\]")
        self.assertRegex(block, r"line \[.*-4\]")

    def test_x_axis_ascending(self):
        body = chart_section(prepare("2026-06-h1"), "趋势")
        block = body.split("```mermaid", 1)[1].split("```", 1)[0]
        axis = re.search(r"x-axis \[([^\]]*)\]", block).group(1)
        periods = [p.strip() for p in axis.split(",")]
        self.assertEqual(periods, sorted(periods), "x 轴必须按期次升序")

    def test_household_charts_are_single_line_and_named(self):
        """xychart-beta 没有图例 ⇒ 两条线画一张图无法分辨，必须拆成两张单线图。"""
        body = chart_section(prepare("2026-06-h1"), "趋势")
        self.assertIn("住户中长期", body)
        self.assertIn("住户短期", body)
        for block in body.split("```mermaid")[2:]:
            chart = block.split("```", 1)[0]
            self.assertEqual(chart.count("line ["), 1, "每张图恰一条 line")

    def test_entries_missing_inputs_are_skipped_and_counted(self):
        contract = load_fixture("2026-06-h1")
        history = load_history("2026-06-h1")
        history["same_type"] = list(history["same_type"]) + [
            {"meta": {"period": "2019-06", "caliber_version": "2015-01"}, "data": {}}]
        md = P.render_trend_scissors(contract, history)
        self.assertNotIn("2019-06", md)
        self.assertIn("共", md)


class TSFStructure(unittest.TestCase):
    """社融增量结构占比（文本条）。"""

    def test_rows_sorted_by_share_descending(self):
        body = chart_section(prepare("2026-06-h1"), "社融增量结构")
        shares = [float(m) for m in re.findall(r"(\-?\d+\.\d)%", body)]
        self.assertGreater(len(shares), 3)
        self.assertEqual(shares, sorted(shares, reverse=True), "占比必须降序")

    def test_government_bond_share_matches_narrative(self):
        """叙述里引用的 30.9% 必须与本段算出来的一致，两处不能各算各的。"""
        body = chart_section(prepare("2026-06-h1"), "社融增量结构")
        self.assertRegex(body, r"政府债券.*30\.9%")


class ChartsProtection(unittest.TestCase):
    """图表段不发 check 行，靠封条保护——这条要实证，不能只写在文档里。"""

    def test_check_line_count_unchanged(self):
        md = prepare("2026-06-h1")
        self.assertEqual(md.count("<!-- check:"), 2, "加图后 check 行仍恰好 2 条")

    def test_charts_live_inside_machine_region_before_narrative(self):
        md = prepare("2026-06-h1")
        machine = md.split(P.BEGIN, 1)[1].split(P.NARR_OPEN, 1)[0]
        self.assertIn("## 趋势", machine)
        self.assertIn("## 社融增量结构", machine)

    def test_verify_rejects_a_tampered_chart(self):
        """图表段没有 check 行，保护全靠封条——这条必须实证到 `verify.py` 这一层。

        ⚠️ 不能用 `seal_of()` 比对：它读的是文件里**存储**的封条值，改正文不会改它，
        那样写出来的断言恒过。要问的是「重算之后 verify 认不认」。"""
        md = prepare("2026-06-h1")
        with tempfile.TemporaryDirectory() as d:
            ok = os.path.join(d, "ok.md")
            bad = os.path.join(d, "bad.md")
            with open(ok, "w", encoding="utf-8") as fh:
                fh.write(md)
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(md.replace("xychart-beta", "xychart-beta\n    %% 伪造", 1))
            verify = os.path.join(HERE, "verify.py")
            self.assertEqual(run([verify, ok], check=False).returncode, 0, "未改动的应通过")
            self.assertEqual(run([verify, bad], check=False).returncode, 1,
                             "改图表必须被封条拦下，否则机器区出现无保护段")


class DisplayWidth(unittest.TestCase):
    """🔴 中文是双宽字符，`%-Ns` 按**字符数**补齐 ⇒ 列会参差。
    文本条的全部价值就是一眼扫过去，列不齐等于白画。"""

    @staticmethod
    def dwidth(s):
        import unicodedata
        return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

    def test_pad_counts_display_columns_not_chars(self):
        self.assertEqual(self.dwidth(P.pad("政府债券", 16)), 16)
        self.assertEqual(self.dwidth(P.pad("对实体人民币贷款", 16)), 16)
        self.assertEqual(self.dwidth(P.pad("abc", 6)), 6)

    def test_pad_does_not_truncate_when_too_long(self):
        """超宽不截断——截断会把「未贴现承兑汇票」砍成看不懂的半个词。"""
        self.assertEqual(P.pad("未贴现承兑汇票", 4), "未贴现承兑汇票")

    def test_signal_bar_column_aligns(self):
        body = chart_section(prepare("2026-06-h1"), "信号")
        # ⚠️ 必须同时要求「含条形字符」：`## 信号` 段开头那句摘要也以「活化」开头，
        # 只按前缀取会把它算进来，得到一个假的不对齐。
        rows = [l for l in body.splitlines()
                if l.startswith(("活化", "楼市", "消费", "信贷")) and ("░" in l or "█" in l)]
        self.assertEqual(len(rows), 4)
        starts = {self.dwidth(l.split("░")[0].split("█")[0]) for l in rows}
        self.assertEqual(len(starts), 1, f"四行的条形起始列不一致: {starts}")

    def test_tsf_bar_column_aligns(self):
        body = chart_section(prepare("2026-06-h1"), "社融增量结构")
        rows = [l for l in body.splitlines() if "亿元" in l and ("░" in l or "█" in l)]
        self.assertGreater(len(rows), 3)
        starts = {self.dwidth(l.split("░")[0].split("█")[0]) for l in rows}
        self.assertEqual(len(starts), 1, f"各行的条形起始列不一致: {starts}")


class TrendMissingValues(unittest.TestCase):
    """🔴 `monthly_average` 缺值时返回 **(0, False)**——第二个元素才是「取到没取到」。
    只判 `v is None` 会把缺期画成 0，在图上造出一个**假的谷底**，而读者无从分辨
    「这个月真的是 0」和「这个月没数据」。"""

    def test_periods_missing_both_calibers_are_skipped(self):
        contract = load_fixture("2023-08-monthly")
        history = load_history("2023-08-monthly")
        missing = [e["meta"]["period"] for e in history["same_type"]
                   if e["data"].get("loan_hh_mlt_ytd") is None
                   and e["data"].get("loan_hh_mlt_mom") is None]
        self.assertTrue(missing, "夹具前置：该侧车里应当有两个口径都缺的期次")

        md = P.render_trend_household(contract, history, "loan_hh_mlt_ytd",
                                      "loan_hh_mlt_mom", "住户中长期贷款", 2000)
        axis = re.search(r"x-axis \[([^\]]*)\]", md).group(1)
        on_axis = {p.strip() for p in axis.split(",")}
        for p in missing:
            self.assertNotIn(p, on_axis, f"{p} 两个口径都缺，不该出现在 x 轴上")

    def test_no_fabricated_zero_in_series(self):
        contract = load_fixture("2023-08-monthly")
        history = load_history("2023-08-monthly")
        md = P.render_trend_household(contract, history, "loan_hh_mlt_ytd",
                                      "loan_hh_mlt_mom", "住户中长期贷款", 2000)
        values = re.search(r"line \[([^\]]*)\]", md).group(1)
        reals = [e["data"].get("loan_hh_mlt_mom") for e in history["same_type"]]
        self.assertNotIn(0, [v for v in reals if v is not None],
                         "夹具前置：真实值里没有 0，所以图上出现 0 必然是补出来的")
        self.assertNotIn("0,", values + ",", "序列里不该出现补零")
