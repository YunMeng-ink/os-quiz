#!/usr/bin/env python3
"""
parse_questions.py — 解析《操作系统复习题集》+《操作系统参考答案》
输出结构化 questions.json 供前端使用。

用法: python parse_questions.py
"""

import re
import json
from pathlib import Path

BASE = Path(__file__).parent
Q_FILE = BASE / "操作系统复习题集.md"
A_FILE = BASE / "操作系统参考答案.md"
OUT = BASE / "questions.json"

# ─── 类型常量 ───────────────────────────────────────────────────
TYPE_MAP = {
    "一、选择题": "choice",
    "二、填空题": "fill",
    "三、判断题": "judge",
    "四、简答题": "short",
    "五、应用题/综合应用题": "apply",
    "六、算法设计题": "algo",
}
TYPE_LABEL = {v: k for k, v in TYPE_MAP.items()}

# ─── 工具函数 ────────────────────────────────────────────────────


def extract_chapter_num(header: str) -> int:
    m = re.search(r"第\s*(\d+)\s*章", header)
    return int(m.group(1)) if m else 0


def strip_md(s: str) -> str:
    return s.strip().rstrip("\\")


def split_inline_options(options: list[str]) -> list[str]:
    """拆分同一行内合并的多个选项（如 'A. xx  B. yy  C. zz  D. ww'）。"""
    result = []
    opt_splitter = re.compile(r"\s{2,}(?=[B-Db-d]\.\s)")
    for opt in options:
        parts = opt_splitter.split(opt)
        result.extend(parts)
    return result


def strip_option_prefix(opt: str) -> str:
    """去掉选项前缀字母（'A. '、'B. ' 等），只保留内容。"""
    m = re.match(r"^\s*[A-Da-d]\.\s+", opt)
    if m:
        return opt[m.end() :].strip()
    return opt.strip()


def count_blanks(text: str) -> int:
    return text.count("______")


# ─── 问题库解析 ──────────────────────────────────────────────────


def parse_questions():
    text = Q_FILE.read_text(encoding="utf-8")
    lines = text.split("\n")

    questions = []
    current_type = None
    current_chapter = 0
    current_chapter_name = ""
    current = None
    in_table = False

    h1_re = re.compile(r"^#\s+(.+)$")
    h2_re = re.compile(r"^##\s+(.+)$")
    qstart_re = re.compile(r"^(\d+)\.\s+(.*)")

    def flush():
        nonlocal current, in_table
        if current and current.get("text_lines"):
            text_lines = current["text_lines"]
            merged = merge_text_lines(current["type"], text_lines)
            current["questionMD"] = merged
            current["blocks"] = parse_blocks(current["type"], merged)
            if current["type"] == "fill":
                current["blankCount"] = count_blanks(merged)
            questions.append(current)
        current = None
        in_table = False

    for line in lines:
        # h1: 题型切换
        m1 = h1_re.match(line)
        if m1:
            flush()
            h1_text = m1.group(1).strip()
            current_type = TYPE_MAP.get(h1_text)
            current_chapter = 0
            current_chapter_name = ""
            continue

        # h2: 章节切换
        m2 = h2_re.match(line)
        if m2:
            flush()
            current_chapter = extract_chapter_num(m2.group(1))
            current_chapter_name = m2.group(1).strip()
            continue

        if current_type is None:
            continue

        # 空行：如果正在 table 中则结束 table
        if not line.strip():
            if in_table:
                in_table = False
            if current:
                current["text_lines"].append("")
            continue

        # 表格行 (仅应用题/算法题可能)
        is_table_line = line.startswith("|") and line.endswith("|")
        if is_table_line and current_type in ("apply", "algo", "short"):
            if current is None:
                # 表格出现在问题外，忽略
                continue
            current["text_lines"].append(line)
            in_table = True
            continue
        else:
            in_table = False

        # 新问题开始
        mq = qstart_re.match(line)
        if mq:
            flush()
            num = int(mq.group(1))
            rest = mq.group(2).strip()
            current = {
                "type": current_type,
                "chapter": current_chapter,
                "chapterName": current_chapter_name,
                "number": num,
                "text_lines": [rest] if rest else [],
                "questionMD": "",
                "blocks": [],
                "options": [],
                "answer": "",
                "explanation": "",
                "blankCount": 0,
            }
            continue

        # 选择题选项行
        opt_re = re.compile(r"^\s{2,}([A-D])\.\s+(.*)")
        mo = opt_re.match(line)
        if mo and current and current["type"] == "choice":
            raw_opts = split_inline_options([f"{mo.group(1)}. {mo.group(2).strip()}"])
            current["options"].extend(raw_opts)
            current["text_lines"].append(line)
            continue

        # 普通行 → 追加到当前问题
        if current:
            current["text_lines"].append(line)

    flush()
    return questions


def merge_text_lines(qtype: str, lines: list[str]) -> str:
    """将文本行合并为完整的 Markdown 文本。"""
    result = []
    for line in lines:
        result.append(line)
    return "\n".join(result).strip()


# ─── 表格解析 ────────────────────────────────────────────────────


def parse_blocks(qtype: str, md: str) -> list[dict]:
    """将问题 Markdown 解析为 blocks 数组。"""
    blocks = []
    lines = md.split("\n")
    i = 0
    # 收集纯文本行
    text_buf = []

    def flush_text():
        if text_buf:
            t = "\n".join(text_buf).strip()
            if t:
                blocks.append({"type": "text", "content": t})
            text_buf.clear()

    while i < len(lines):
        line = lines[i]
        # 检测表格块
        if line.startswith("|") and line.endswith("|"):
            table_lines = []
            while (
                i < len(lines) and lines[i].startswith("|") and lines[i].endswith("|")
            ):
                table_lines.append(lines[i].strip())
                i += 1
            block = parse_table(table_lines)
            if block:
                flush_text()
                blocks.append(block)
            continue
        # 检测选项（选择题专用）
        opt_re = re.compile(r"^\s{2,}[A-D]\.\s")
        if qtype == "choice" and opt_re.match(line):
            text_buf.append(line)
            i += 1
            continue
        # 普通文本
        text_buf.append(line)
        i += 1

    flush_text()

    if qtype == "choice" and not any(b["type"] == "options" for b in blocks):
        rebuild_choice_blocks(blocks, md)

    return blocks


def rebuild_choice_blocks(blocks: list[dict], md: str):
    """将选择题的文本+选项行重组为 text + options blocks。"""
    opt_re = re.compile(r"^\s{2,}([A-D])\.\s+(.*)")
    lines = md.split("\n")
    new_blocks = []
    text_lines = []
    options = []
    for line in lines:
        mo = opt_re.match(line)
        if mo:
            raw_opts = split_inline_options([f"{mo.group(1)}. {mo.group(2).strip()}"])
            options.extend(raw_opts)
        else:
            if options:
                if text_lines:
                    t = "\n".join(text_lines).strip()
                    if t:
                        new_blocks.append({"type": "text", "content": t})
                    text_lines = []
                new_blocks.append({"type": "options", "options": options})
                options = []
            text_lines.append(line)
    if text_lines:
        t = "\n".join(text_lines).strip()
        if t:
            new_blocks.append({"type": "text", "content": t})
    if options:
        new_blocks.append({"type": "options", "options": options})
    if new_blocks:
        blocks.clear()
        blocks.extend(new_blocks)


def parse_table(lines: list[str]) -> dict | None:
    """解析 Markdown 表格行，返回 table block。"""
    if len(lines) < 2:
        return None

    def split_row(row: str) -> list[str]:
        parts = row.strip("|").split("|")
        return [p.strip() for p in parts]

    headers = split_row(lines[0])
    align_line = split_row(lines[1]) if len(lines) > 1 else []
    align = []
    for cell in align_line:
        cell = cell.strip()
        if cell.startswith(":") and cell.endswith(":"):
            align.append("center")
        elif cell.startswith(":"):
            align.append("left")
        elif cell.endswith(":"):
            align.append("right")
        else:
            align.append("left")

    rows = []
    for row in lines[2:]:
        rows.append(split_row(row))

    return {
        "type": "table",
        "headers": headers,
        "align": align,
        "rows": rows,
    }


# ─── 答案库解析 ──────────────────────────────────────────────────


def parse_answers():
    """
    返回 dict: (type, number) → {answer, explanation}
    使用 First-Win 策略：同一 (type, number) 首次出现生效（后续辅助章节不覆盖）。
    """
    text = A_FILE.read_text(encoding="utf-8")

    ANSWER_TYPE_MAP = {
        "一、选择题答案": "choice",
        "二、填空题答案": "fill",
        "三、判断题答案": "judge",
        "四、简答题参考答案": "short",
        "五、应用题/综合应用题参考答案": "apply",
        "六、算法设计题参考答案": "algo",
    }

    answers = {}
    h1_re = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    sections = list(h1_re.finditer(text))

    for i, sec in enumerate(sections):
        if i == 0:
            continue

        sec_start = sec.end()
        sec_end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        sec_text = text[sec_start:sec_end]
        h1_text = sec.group(1).strip()

        qtype = ANSWER_TYPE_MAP.get(h1_text)
        if qtype is None:
            continue

        if qtype == "fill":
            deriv_pos = sec_text.find("### 填空题推导过程")
            if deriv_pos != -1:
                sec_text = sec_text[:deriv_pos]

        if qtype in ("choice", "judge", "fill"):
            rows = parse_answer_table_rows(sec_text)
            for row in rows:
                if len(row) >= 2:
                    try:
                        num = int(row[0].strip())
                        ans = row[1].strip()
                        expl = row[2].strip() if len(row) >= 3 else ""
                        key = (qtype, num)
                        if key not in answers:
                            answers[key] = {
                                "answer": ans,
                                "explanation": expl,
                            }
                    except ValueError:
                        continue

        elif qtype in ("short", "apply", "algo"):
            chapters = split_answer_by_chapter(sec_text)
            for chap_num, chap_text in chapters:
                q_blocks = re.split(r"(?=^###\s+\d+\.)", chap_text, flags=re.MULTILINE)
                for block in q_blocks:
                    block = block.strip()
                    if not block:
                        continue
                    m = re.match(r"^###\s+(\d+)\.\s*(.*)", block)
                    if m:
                        num = int(m.group(1))
                        body = re.sub(r"^###\s+\d+\..*", "", block, count=1).strip()
                        key = (qtype, num)
                        if key not in answers:
                            answers[key] = {
                                "answer": body,
                                "explanation": "",
                            }

    return answers


def parse_answer_table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and not re.match(r"^:?-+:?$", cells[0].strip()):
                if len(cells) >= 2:
                    rows.append(cells)
    return rows


def split_answer_by_chapter(text: str) -> list[tuple[int, str]]:
    chapters = []
    h2_re = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    parts = list(h2_re.finditer(text))
    for i, m in enumerate(parts):
        chap_num = extract_chapter_num(m.group(1))
        start = m.end()
        end = parts[i + 1].start() if i + 1 < len(parts) else len(text)
        chapters.append((chap_num, text[start:end].strip()))
    return chapters


# ─── 主流程 ──────────────────────────────────────────────────────


def main():
    print("解析题库...")
    questions = parse_questions()
    print(f"  题库提取 {len(questions)} 道题")

    print("解析答案...")
    answers = parse_answers()
    print(f"  答案提取 {len(answers)} 条")

    # 生成 id + 关联答案
    type_counter: dict[str, int] = {}
    matched = 0
    for q in questions:
        t = q["type"]
        type_counter[t] = type_counter.get(t, 0) + 1
        q["id"] = f"{t}-{type_counter[t]}"

        # (type, number) 全局唯一，直接匹配
        key = (q["type"], q["number"])
        ans = answers.get(key)
        if ans:
            q["answer"] = ans["answer"]
            q["explanation"] = ans["explanation"]
            matched += 1

    print(f"  成功关联 {matched}/{len(questions)} 题")

    # 统计
    stats = {"total": len(questions), "byType": {}, "byChapter": {}}
    for q in questions:
        t = q["type"]
        stats["byType"][t] = stats["byType"].get(t, 0) + 1
        c = q["chapter"]
        stats["byChapter"][c] = stats["byChapter"].get(c, 0) + 1

    # 输出清理 & 答案归一化
    for q in questions:
        # 移除前端不需要的字段
        q.pop("text_lines", None)
        q.pop("chapterName", None)
        q.pop("options", None)
        # 填空题答案统一为数组（多空用 `；` 分隔）
        if q["type"] == "fill" and q.get("answer") and isinstance(q["answer"], str):
            ans_parts = [a.strip() for a in q["answer"].split("；")]
            bc = q.get("blankCount") or 1
            # 若答案条目数超过空白数，剔除出现在题干中的条目（冗余题面文字）
            if len(ans_parts) > bc:
                qmd = q.get("questionMD", "")
                ans_parts = [a for a in ans_parts if a not in qmd]
            q["answer"] = ans_parts
        # 判断题答案归一化
        if q["type"] == "judge" and q.get("answer"):
            q["answer"] = (
                "正确" if q["answer"] in ("正确", "对", "true", "True") else "错误"
            )

    output = {
        "version": "1.0",
        "generated": __import__("datetime").date.today().isoformat(),
        "stats": stats,
        "questions": questions,
    }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n输出: {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")

    print("\n=== 统计 ===")
    for t, cnt in sorted(stats["byType"].items()):
        print(f"  {TYPE_LABEL.get(t, t)}: {cnt}")
    print(f"  合计: {stats['total']}")
    for c in sorted(stats["byChapter"]):
        print(f"  第{c}章: {stats['byChapter'][c]}")

    # 无答案题目
    no_ans = [q for q in questions if not q.get("answer")]
    if no_ans:
        print(f"\n⚠ 未关联答案的题目 ({len(no_ans)}):")
        by_type_nums = {}
        for q in no_ans:
            by_type_nums.setdefault(q["type"], []).append(q["number"])
        for t, nums in sorted(by_type_nums.items()):
            nums.sort()
            print(f"  {TYPE_LABEL.get(t, t)} ({len(nums)}): {nums}")

    # 简答题/应用题未匹配详情
    for t in ("short", "apply"):
        q_nums_without = sorted(
            [q["number"] for q in questions if q["type"] == t and not q.get("answer")]
        )
        if q_nums_without:
            print(
                f"\n  {TYPE_LABEL.get(t, t)} 无答案题号 ({len(q_nums_without)}): {q_nums_without}"
            )


if __name__ == "__main__":
    main()
