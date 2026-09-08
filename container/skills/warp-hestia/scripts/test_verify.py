#!/usr/bin/env python3
"""verify.py 的 unittest。M3 的 TASK-005。只用标准库。

done_criteria → 测试映射（防护性写入，验证者逐条对照用）：
  functional[0] 只用标准库 / 作用域与 note-format.md 逐字一致 → StdlibOnly, ScopeMatchesSpec
  functional[1] 四态                                        → FourStates（①未改 ②改表 ③改叙述 ④删除类四种）
  functional[2] 必须 import prepare 复用，不得另写一份         → ReusesPrepare
  boundary      格式损坏 / 多条 check 或第二条 seal / 批注区不参与 → Boundary
  error_handling 文件不存在 / 非笔记 / 空文件                   → BadInput

🔴 校验行条数**写死**（check 恰 2、seal 恰 1），**不从文档结构推 N**——结构本身就是被篡改对象。
"""
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
VERIFY = os.path.join(HERE, "verify.py")

sys.path.insert(0, HERE)


def run(args, check=True):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, check=check)


def prepare(name, extra=()):
    return run([PREP, f"{FIX}/{name}.json", f"{FIX}/{name}.history.json",
                "--now", "2026-09-12", *extra]).stdout


def verify_text(md):
    """把内容写进**独立临时文件**再验。⚠️ 不用固定的 /tmp 路径——固定路径会让并发或
    上一轮的残留文件冒充本轮输入，产生假 PASS。"""
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(md)
        return run([VERIFY, path], check=False)
    finally:
        os.unlink(path)


def first_marker_line(md, prefix):
    """取第一条以 prefix 开头的校验行（不含行尾换行）。"""
    return next(l for l in md.splitlines() if l.startswith(prefix))


def verify_src():
    with open(VERIFY, encoding="utf-8") as fh:
        return fh.read()


class StdlibOnly(unittest.TestCase):
    def test_only_stdlib_imports(self):
        allowed = {"json", "hashlib", "argparse", "datetime", "re", "os", "sys", "prepare"}
        src = verify_src()
        mods = set()
        for line in src.splitlines():
            m = re.match(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)", line)
            if m:
                mods.add(m.group(1).split(".")[0])
        self.assertEqual(mods - allowed, set(), f"引入了标准库之外的模块: {mods - allowed}")


class ReusesPrepare(unittest.TestCase):
    """functional[2]：必须 import prepare 复用，不得另写一份实现。
    理由：作用域定义一旦有两份，两份必然漂移，而两个漂移方向都致命
    （对合规笔记判红 ⇒ 没人再信它；对被篡改笔记判绿 ⇒ 本任务存在的理由当场失效）。"""

    def test_no_second_definition(self):
        src = verify_src()
        self.assertEqual(len(re.findall(r"^def (?:seal_digest|with_check)\b", src, re.M)), 0,
                         "verify.py 里不得有第二份 seal_digest / with_check 定义")

    def test_imports_prepare(self):
        src = verify_src()
        self.assertRegex(src, r"(?m)^(?:import prepare|from prepare import)\b")

    def test_uses_prepare_functions(self):
        import verify
        import prepare
        self.assertIs(verify.prepare.seal_digest, prepare.seal_digest)
        self.assertIs(verify.prepare.with_check, prepare.with_check)


class ScopeMatchesSpec(unittest.TestCase):
    """functional[0]：作用域与 note-format.md / prepare.py 逐字一致。"""

    def test_check_scope_is_from_previous_heading(self):
        import prepare
        md = prepare_golden("2026-06-h1")
        for title in ["本期数据", "前 12 期"]:
            with self.subTest(title):
                body, rest = md.split(f"## {title}\n", 1)[1].split("<!-- check: ", 1)
                got = rest.split(" -->", 1)[0]
                want_line = prepare.with_check(f"## {title}\n" + body).rstrip("\n").splitlines()[-1]
                self.assertEqual(want_line, f"<!-- check: {got} -->")

    def test_seal_scope_excludes_narrative(self):
        import prepare
        md = prepare_golden("2026-06-h1")
        seal = md.split("<!-- seal: ", 1)[1].split(" -->", 1)[0]
        self.assertEqual(prepare.seal_digest(md), seal)


def prepare_golden(name):
    with open(os.path.join(GOLDEN, f"{name}.md"), encoding="utf-8") as fh:
        return fh.read()


class FourStates(unittest.TestCase):
    """functional[1]：四态。"""

    def setUp(self):
        self.md = prepare_golden("2026-06-h1")

    # ① 未改动 ⇒ 0
    def test_1_untouched_exits_zero(self):
        r = verify_text(self.md)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_1_untouched_both_goldens(self):
        for name in ["2026-06-h1", "2023-08-monthly"]:
            with self.subTest(name):
                self.assertEqual(verify_text(prepare_golden(name)).returncode, 0)

    def test_1_freshly_generated_also_passes(self):
        """不只 golden——现场生成的输出也必须过（否则只是把 golden 背下来了）。"""
        self.assertEqual(verify_text(prepare("2025-12-annual")).returncode, 0)

    # ② 表内数字被改 ⇒ 1 且含 check
    def test_2_edited_table_number(self):
        # ⚠️ 需求原文用的 `462.06` 在实际输出里**不存在**（作者臆想值）；改用表内真实值 2212
        self.assertIn("| 2212 |", self.md)
        r = verify_text(self.md.replace("2212", "9999", 1))
        self.assertEqual(r.returncode, 1)
        self.assertIn("check", r.stdout + r.stderr)

    def test_2_edited_history_table(self):
        """第二张表被改也要红（两条 check 都得真的在比）。"""
        r = verify_text(self.md.replace("| 2025-06 | 2025-01 |", "| 2025-06 | 1999-01 |", 1))
        self.assertEqual(r.returncode, 1)
        self.assertIn("check", r.stdout + r.stderr)

    # ③ 只改 narrative ⇒ 0（含在其中写 ## 小标题）
    def test_3_narrative_edit_ok(self):
        r = verify_text(self.md.replace("<!-- narrative -->",
                                        "<!-- narrative -->\n这是模型写的叙述。", 1))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_3_narrative_with_markdown_headings_ok(self):
        """🔴 methodology 的八问框架天然诱导模型在叙述里写 `## ` 小标题——必须不受影响。"""
        essay = ("<!-- narrative -->\n"
                 "## （一）经济是在扩张，还是在收缩？\n住户存款与住户贷款一升一降。\n\n"
                 "## （二）房地产是否真正复苏？\n住户中长期贷款月均 368.67 亿元。\n")
        r = verify_text(self.md.replace("<!-- narrative -->", essay, 1))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ④ 删除类篡改 ⇒ 1（四种）
    def test_4a_delete_one_check_line(self):
        line = first_marker_line(self.md, "<!-- check: ")
        r = verify_text(self.md.replace(line + "\n", "", 1))
        self.assertEqual(r.returncode, 1, "删一条 check 行必须红")

    def test_4b_delete_whole_section(self):
        """删整段（`## ` 标题 + 表 + 它的 check 行）——分段 check 各自仍自洽，只有封条抓得住。"""
        head, rest = self.md.split("## 前 12 期\n", 1)
        _, tail = rest.split("<!-- check: ", 1)
        tail = tail.split(" -->\n", 1)[1]
        r = verify_text(head + tail)
        self.assertEqual(r.returncode, 1, "删整段必须红")

    def test_4c_edit_signal_section(self):
        """`## 信号` 段依 spec §6.2 **没有** check 行保护——只有封条能抓。"""
        self.assertIn("温度 1/4", self.md)
        r = verify_text(self.md.replace("温度 1/4", "温度 4/4", 1))
        self.assertEqual(r.returncode, 1, "改无 check 保护的信号段必须红")

    def test_4d_delete_seal_line(self):
        line = first_marker_line(self.md, "<!-- seal: ")
        r = verify_text(self.md.replace(line + "\n", "", 1))
        self.assertEqual(r.returncode, 1, "删封条必须红")

    def test_4_error_message_identifies_where(self):
        """报错要指出是哪一段/是否封条，以及期望与实得的 hex。"""
        r = verify_text(self.md.replace("2212", "9999", 1))
        out = r.stdout + r.stderr
        self.assertIn("本期数据", out)
        self.assertRegex(out, r"[0-9a-f]{64}")


class Boundary(unittest.TestCase):
    """boundary 三条。"""

    def setUp(self):
        self.md = prepare_golden("2026-06-h1")

    def test_malformed_check_reports_format_error(self):
        """🔴 格式损坏必须报**格式错**，不得当成「没有校验行」而放行。"""
        line = first_marker_line(self.md, "<!-- check: ")
        for bad in ["<!-- check: zzz -->",                       # 非 hex
                    "<!-- check: abc123 -->",                    # 长度不对
                    "<!-- check: " + "a" * 64]:                  # 缺 -->
            with self.subTest(bad[:24]):
                r = verify_text(self.md.replace(line, bad, 1))
                self.assertEqual(r.returncode, 1)
                self.assertIn("格式", r.stdout + r.stderr)

    def test_malformed_seal_reports_format_error(self):
        line = first_marker_line(self.md, "<!-- seal: ")
        r = verify_text(self.md.replace(line, "<!-- seal: nothex -->", 1))
        self.assertEqual(r.returncode, 1)
        self.assertIn("格式", r.stdout + r.stderr)

    def test_duplicate_check_in_same_section(self):
        """同一段出现多个 check ⇒ 判为被篡改，**不取第一个也不取最后一个**。"""
        line = first_marker_line(self.md, "<!-- check: ")
        r = verify_text(self.md.replace(line + "\n", line + "\n" + line + "\n", 1))
        self.assertEqual(r.returncode, 1)

    def test_two_checks_both_in_one_section(self):
        """🔴 变异逼出来的缺口：`test_duplicate_check_in_same_section` 只是**复制**一条 check，
        总数变 3 ⇒ 被「恰好 2 条」那条更早的判据挡下，**「同段多于一条」这条从未被行使**
        （把它停掉的变异 V4 因此存活）。这里构造**总数仍为 2、但两条都在第一段**的输入。"""
        lines = self.md.splitlines(keepends=True)
        idx = [i for i, l in enumerate(lines) if l.startswith("<!-- check: ")]
        self.assertEqual(len(idx), 2, "夹具前提：原本恰 2 条")
        first, second = idx
        out = lines[:first + 1] + [lines[first]] + lines[first + 1:second] + lines[second + 1:]
        md2 = "".join(out)
        self.assertEqual(md2.count("<!-- check: "), 2, "构造后总数仍须为 2")
        r = verify_text(md2)
        self.assertEqual(r.returncode, 1)
        self.assertIn("多于一条", r.stdout + r.stderr)

    def test_check_line_outside_machine_zone(self):
        """🔴 同上：把一条 check 行**移到机器区之外**（总数仍 2、封条仍 1），
        钉住「校验行必须落在机器区内」这条——它同样被更早的判据遮蔽过（变异 V7 存活）。"""
        lines = self.md.splitlines(keepends=True)
        idx = [i for i, l in enumerate(lines) if l.startswith("<!-- check: ")]
        moved = lines[idx[1]]
        out = lines[:idx[1]] + lines[idx[1] + 1:] + [moved]
        md2 = "".join(out)
        self.assertEqual(md2.count("<!-- check: "), 2)
        self.assertEqual(md2.count("<!-- seal: "), 1)
        r = verify_text(md2)
        self.assertEqual(r.returncode, 1)
        self.assertIn("机器区之外", r.stdout + r.stderr)

    def test_second_seal(self):
        line = first_marker_line(self.md, "<!-- seal: ")
        r = verify_text(self.md.replace(line + "\n", line + "\n" + line + "\n", 1))
        self.assertEqual(r.returncode, 1)

    def test_annotation_area_not_verified(self):
        """批注区是人写的、每次都会变 ⇒ 不参与校验。"""
        self.assertTrue(self.md.rstrip().endswith("（手写区，永不被覆盖）"))
        r = verify_text(self.md + "\n又加了一行手写批注。\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class BadInput(unittest.TestCase):
    """error_handling 三条：都要非零，且**不是 traceback**。"""

    def test_missing_file(self):
        r = run([VERIFY, "/nonexistent/note.md"], check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("/nonexistent/note.md", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_not_a_note(self):
        r = verify_text("这只是一段普通文字，没有 frontmatter，也没有机器区。\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue((r.stdout + r.stderr).strip())

    def test_empty_file(self):
        """🔴 断言必须查**消息**而不只是退出码：空文件分支与「不是笔记格式」分支给出**相同退出码**
        ⇒ 只断言 `!= 0` 时，把空文件分支整个删掉的变异（V9）会**存活**——两条路径在退出码上不可区分。
        这与「口径标注」那次同形：专职断言恒真，真正杀死变异的是别的东西。"""
        r = verify_text("")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("空文件", r.stdout + r.stderr)

    def test_empty_and_not_a_note_give_different_messages(self):
        """两条输入错误路径必须可区分——否则其中一条等于不存在。"""
        empty = verify_text("")
        junk = verify_text("这只是一段普通文字。\n")
        self.assertIn("空文件", empty.stdout + empty.stderr)
        self.assertIn("不是笔记格式", junk.stdout + junk.stderr)
        self.assertNotIn("空文件", junk.stdout + junk.stderr)


if __name__ == "__main__":
    unittest.main()
