#!/usr/bin/env python3
"""校验笔记的机器区未被改动——写回 vault 之前的最后一道闸。M3 的 TASK-005。

只用标准库 + 同目录的 `prepare`。

🔴 **作用域定义不在本文件里重新实现**——`seal_digest` 与 `with_check` 一律从 `prepare` 导入。
理由：这两个定义一旦存在两份，两份**必然漂移**，而漂移的两个方向都致命——
对合规笔记判红（人不再信这道闸）、对被篡改笔记判绿（这道闸存在的理由当场失效）。
规格的唯一真相源是 `references/note-format.md`，`prepare.py` 是它的实现，本文件是它的消费者。

判据（**条数写死，不从文档结构推**——结构本身就是被篡改的对象）：
  (i)   分段 check **恰好 2 条**、封条 seal **恰好 1 条**；数量不符即判被篡改
  (ii)  逐条验分段 check：作用域 = 从**上一个 `## ` 标题行**起，到该 check 行**之前**
  (iii) 验封条 seal：作用域 = 从 `<!-- machine-generated: begin -->` 的**下一行**起、到 seal 行之前，
        **扣除** `<!-- narrative -->` 与 `<!-- /narrative -->` 之间（含这两行）的全部文本

封条是**删除类篡改的唯一防线**：删一条 check 行、删整段（标题+表+check）、改无 check 保护的
`## 信号` 段——分段 check 各自仍自洽，只有封条覆盖的文本会变。而 narrative 被扣除，
所以模型按 methodology 的八问框架写叙述（哪怕在里面写 `## ` 小标题）都不受影响。

退出码：0 全部匹配；1 被篡改或格式损坏；2 输入不可用（文件不存在 / 空 / 不是笔记）。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prepare  # noqa: E402  —— 必须在 sys.path 插入之后

CHECK_PREFIX = "<!-- check:"
SEAL_PREFIX = "<!-- seal:"
CHECK_RE = re.compile(r"^<!-- check: ([0-9a-f]{64}) -->$")
SEAL_RE = re.compile(r"^<!-- seal: ([0-9a-f]{64}) -->$")
HEADING_PREFIX = "## "

EXPECT_CHECKS = 2   # `## 本期数据` 与 `## 前 12 期`；`## 信号` 段依 spec §6.2 不发
EXPECT_SEALS = 1


def fail(msg, code=1):
    sys.stderr.write(msg + "\n")
    return code


def scan_markers(lines):
    """收集 check / seal 行的下标。**格式损坏与「没有校验行」必须区分**：
    凡以标记前缀开头却不满足严格形态的行，一律报格式错，不得当成「这里没有校验行」而放行。"""
    checks, seals, malformed = [], [], []
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        for prefix, pattern, bucket in ((CHECK_PREFIX, CHECK_RE, checks),
                                        (SEAL_PREFIX, SEAL_RE, seals)):
            if not stripped.startswith(prefix):
                continue
            m = pattern.match(stripped)
            # 合法的存 (行号, hex)；损坏的存 (行号, 整行) 供报错原样回显
            if m:
                bucket.append((i, m.group(1)))
            else:
                malformed.append((i, stripped))
            break
    return checks, seals, malformed


def verify(md, path):
    if not md.strip():
        return fail("空文件，没有可校验的内容: %s" % path, 2)
    if prepare.BEGIN not in md or prepare.END not in md:
        return fail("不是笔记格式：缺少机器区标记 `%s` / `%s`: %s"
                    % (prepare.BEGIN, prepare.END, path), 2)

    lines = md.splitlines(keepends=True)      # 行尾保留，check 的作用域要逐字节还原
    bare = [line.rstrip("\n") for line in lines]
    begin_i = bare.index(prepare.BEGIN)
    end_i = bare.index(prepare.END)

    checks, seals, malformed = scan_markers(lines)

    if malformed:
        for i, line in malformed:
            sys.stderr.write("第 %d 行校验行**格式**损坏（应为 `<!-- check: <64 位小写 hex> -->` "
                             "或 `<!-- seal: … -->`）: %s\n" % (i + 1, line))
        return 1

    # (i) 条数写死
    if len(checks) != EXPECT_CHECKS:
        return fail("分段 check 行应为 %d 条，实得 %d 条 —— 判为被篡改（条数不从文档结构推）"
                    % (EXPECT_CHECKS, len(checks)))
    if len(seals) != EXPECT_SEALS:
        return fail("封条 seal 行应为 %d 条，实得 %d 条 —— 判为被篡改"
                    % (EXPECT_SEALS, len(seals)))

    for i, _hex in checks + seals:
        if not (begin_i < i < end_i):
            return fail("第 %d 行的校验行落在机器区之外 —— 判为被篡改: %s" % (i + 1, bare[i]))

    # (ii) 逐条验分段 check
    seen_sections = set()
    for idx, got_hex in checks:
        heading_i = None
        for j in range(idx - 1, begin_i, -1):
            if bare[j].startswith(HEADING_PREFIX):
                heading_i = j
                break
        if heading_i is None:
            return fail("第 %d 行的 check 行之前没有 `## ` 标题，无法确定作用域 —— 判为被篡改" % (idx + 1))
        title = bare[heading_i][len(HEADING_PREFIX):]
        if heading_i in seen_sections:
            return fail("段「%s」出现了多于一条 check 行 —— 判为被篡改"
                        "（不取第一个也不取最后一个）" % title)
        seen_sections.add(heading_i)

        # 作用域文本仍必须用带行尾的 lines 拼；期望值只经 prepare.with_check 得出，本文件不另算
        scope = "".join(lines[heading_i:idx])
        want_line = prepare.with_check(scope).rstrip("\n").splitlines()[-1]
        want_hex = CHECK_RE.match(want_line).group(1)
        if want_hex != got_hex:
            return fail("段「%s」的 check 不匹配（第 %d 行）：\n  期望 %s\n  实得 %s"
                        % (title, idx + 1, want_hex, got_hex))

    # (iii) 验封条
    seal_i, seal_hex = seals[0]
    want_seal = prepare.seal_digest(md)
    if want_seal != seal_hex:
        return fail("封条 seal 不匹配（第 %d 行）——机器区有删除或改动，且不在任何 check 的覆盖范围内：\n"
                    "  期望 %s\n  实得 %s" % (seal_i + 1, want_seal, seal_hex))
    return 0


def main():
    ap = argparse.ArgumentParser(description="校验笔记机器区未被改动（M3 的 TASK-005）")
    ap.add_argument("note")
    args = ap.parse_args()

    try:
        with open(args.note, encoding="utf-8") as fh:
            md = fh.read()
    except OSError as err:
        sys.stderr.write("读取失败: %s (%s)\n" % (args.note, err.strerror or err))
        return 2

    return verify(md, args.note)


if __name__ == "__main__":
    sys.exit(main())
