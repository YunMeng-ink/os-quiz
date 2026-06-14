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

        elif qtype in ("short", "apply"):
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


# ─── 缺失答案补全 ────────────────────────────────────────────────


def fill_missing_answers(answers: dict) -> dict:
    """补充原始答案文件中缺失的 40 道题答案。"""
    missing: dict[tuple[str, int], dict[str, str]] = {
        # ── 简答题 ──────────────────────────────────────────────
        ("short", 72): {
            "answer": "文件的逻辑结构是指从用户观点出发所观察到的文件组织形式，即用户可以直接处理的数据及其组织形式。逻辑文件主要有两种组织形式：\n\n"
            "（1）**流式文件**：由一串无结构的字节序列构成，用户访问时通过读写指针指定位置。流式文件不区分记录，管理简单，UNIX/Linux 采用此方式。\n\n"
            "（2）**记录式文件**：由若干有结构的逻辑记录组成，每个记录包含一个或多个数据项。记录式文件又可分为：\n"
            "   - 定长记录文件：所有记录长度相同，访问方便；\n"
            "   - 变长记录文件：各记录长度可变，空间利用率高，但管理复杂。",
            "explanation": "",
        },
        ("short", 73): {
            "answer": "顺序存取和随机存取的主要区别：\n\n"
            "（1）**顺序存取**：按文件的逻辑地址依次访问，每次读取或写入后文件指针自动后移。磁带、行式打印机等设备典型采用顺序存取。\n\n"
            "（2）**随机存取（直接存取）**：允许用户直接定位到文件的任意位置进行读写，通过文件偏移量指定访问位置。磁盘文件系统支持随机存取。\n\n"
            "**核心区别**：顺序存取只能线性推进，无法跳转；随机存取可任意定位，效率更高但实现更复杂，适用于需要随机访问的数据结构。",
            "explanation": "",
        },
        ("short", 74): {
            "answer": "**引入 SPOOLing 技术的原因**：\n"
            "慢速独占设备（如打印机）与 CPU 速度严重不匹配，独占设备的串行使用导致资源利用率低，且进程需等待 I/O 完成，阻塞时间长。\n\n"
            "**SPOOLing 技术带来的好处**：\n"
            "（1）**将独占设备改造为共享设备**：通过磁盘上的输入/输出井模拟独占设备，多个用户可同时提交打印任务。\n"
            "（2）**提高了 I/O 速度**：输入/输出操作在高速磁盘上进行，用户进程无需等待慢速设备。\n"
            "（3）**实现了虚拟设备功能**：每个用户感觉自己独占了一台设备（虚拟设备）。\n"
            "（4）**实现了多道程序并行**：CPU 可与 I/O 设备并行工作，提升系统吞吐量。",
            "explanation": "",
        },
        ("short", 75): {
            "answer": "**缓冲**：在内存中开辟一块区域，用于暂存 I/O 数据，以协调 CPU 与 I/O 设备之间速度不匹配的矛盾，减少对 CPU 的中断频率。\n\n"
            "**缓冲技术的主要方式**：\n"
            "（1）**单缓冲**：在内存中设置一个缓冲区，设备和处理器交换数据时，一方写入缓冲区，另一方读取，交替使用。\n"
            "（2）**双缓冲**：设置两个缓冲区，设备和处理器可分别对不同的缓冲区操作，实现数据输入和输出的并行处理。\n"
            "（3）**循环缓冲**：多个缓冲区组成环形队列，生产者与消费者分别在队列两端操作，适用于生产/消费速度相近的场景。\n"
            "（4）**缓冲池**：系统管理一组缓冲区（空闲、输入、输出三队列），动态分配给各进程使用，利用率最高，为现代 OS 广泛采用。",
            "explanation": "",
        },
        # ── 应用题 — P/V 同步互斥 ──────────────────────────────
        ("apply", 7): {
            "answer": "```\nsemaphore mutex = 1;     // 路口互斥，只允许一个方向通过\nsemaphore pedestrian = 0; // 是否有行人在等待\nint waiting_p = 0;        // 等待通过的行人数\n\n// 行人\nvoid pedestrian_proc() {\n    while (true) {\n        P(mutex);\n        waiting_p++;\n        V(pedestrian);\n        V(mutex);\n        通过路口;\n        P(mutex);\n        waiting_p--;\n        V(mutex);\n    }\n}\n\n// 机动车\nvoid vehicle_proc() {\n    while (true) {\n        P(mutex);\n        while (waiting_p > 0) {\n            V(mutex);\n            // 让行人先通过\n            P(pedestrian);\n            P(mutex);\n        }\n        通过路口;\n        V(mutex);\n    }\n}\n```",
            "explanation": "",
        },
        ("apply", 8): {
            "answer": "假设进程同步关系为：P1 → P2,P3 → P4 → P5,P6（线性依赖，具体以试题拓扑图为准）。\n```\nsemaphore S12 = 0, S13 = 0;\nsemaphore S24 = 0, S34 = 0;\nsemaphore S45 = 0, S46 = 0;\n\nP1() { 执行; V(S12); V(S13); }\nP2() { P(S12); 执行; V(S24); }\nP3() { P(S13); 执行; V(S34); }\nP4() { P(S24); P(S34); 执行; V(S45); V(S46); }\nP5() { P(S45); 执行; }\nP6() { P(S46); 执行; }\n```\n具体信号量数量和连接方式随题目给出的前驱图调整。",
            "explanation": "",
        },
        ("apply", 9): {
            "answer": "**会导致死锁的执行次序**：\nP1 占有 R1 申请 R2，P2 占有 R2 申请 R1，两者互相等待。\n\n**修改算法**（按相同顺序申请资源）：\n```\nsemaphore M1 = 1, M2 = 1;\n\n// P1\nP(M1);  // 申请 R1\nP(M2);  // 申请 R2\n使用资源 R1、R2;\nV(M2);\nV(M1);\n\n// P2\nP(M1);  // 先申请 R1，再申请 R2（与 P1 顺序一致）\nP(M2);\n使用资源 R1、R2;\nV(M2);\nV(M1);\n```\n通过**资源按序分配**打破循环等待条件，防止死锁。",
            "explanation": "",
        },
        ("apply", 10): {
            "answer": "```\nsemaphore bowl[N] = {1};          // 每个哲学家一个碗（或中心碗计数）\n// 简化：中心有 m 个碗，取信号量\nsemaphore bowls = m;              // 碗资源\nsemaphore chopstick[n];           // 筷子\nfor (int i = 0; i < n; i++) chopstick[i] = 1;\n\nvoid philosopher(int i) {\n    while (true) {\n        思考;\n        P(bowls);                   // 取碗\n        P(chopstick[i]);            // 取左筷\n        P(chopstick[(i+1) % n]);    // 取右筷\n        就餐;\n        V(chopstick[i]);\n        V(chopstick[(i+1) % n]);\n        V(bowls);\n    }\n}\n```\n当 m < n 时，限制同时就餐人数，可防止死锁。",
            "explanation": "",
        },
        ("apply", 11): {
            "answer": "```\nsemaphore empty = 2000;   // 展馆空位\nsemaphore mutex = 1;      // 出入口互斥\nint x = 0;                // 普通票人数\nint y = 0;                // 学生票人数\nsemaphore diff = 400;     // 控制 0 ≤ x-y ≤ 400\n\n// 普通票进入\nvoid enter_regular() {\n    P(empty);\n    P(mutex);\n    x++;\n    V(mutex);\n    P(diff);               // 维护差值上限\n    进入;\n}\n\n// 普通票离开\nvoid leave_regular() {\n    P(mutex);\n    x--;\n    V(diff);\n    V(mutex);\n    V(empty);\n}\n\n// 学生票进入\nvoid enter_student() {\n    P(empty);\n    P(mutex);\n    y++;\n    V(diff);               // 学生+1 缩小差值\n    V(mutex);\n    进入;\n}\n\n// 学生票离开\nvoid leave_student() {\n    P(mutex);\n    y--;\n    V(mutex);\n    V(empty);\n}\n```",
            "explanation": "",
        },
        ("apply", 12): {
            "answer": "```\nsemaphore empty = 1000;        // 缓冲区空位\nsemaphore full = 0;            // 产品数\nsemaphore mutex = 1;           // 缓冲区互斥\nsemaphore block = 1;           // 连续取10件互斥\nint taken = 0;                 // 已连续取件数\n\nvoid producer() {\n    while (true) {\n        生产产品;\n        P(empty);\n        P(mutex);\n        放入缓冲区;\n        V(mutex);\n        V(full);\n    }\n}\n\nvoid consumer() {\n    while (true) {\n        P(block);               // 开始连续取\n        for (int i = 0; i < 10; i++) {\n            P(full);\n            P(mutex);\n            从缓冲区取出1件产品;\n            V(mutex);\n            V(empty);\n        }\n        V(block);               // 其他消费者可开始取\n    }\n}\n```",
            "explanation": "",
        },
        # ── 应用题 — 调度/死锁/分区 ────────────────────────────
        ("apply", 15): {
            "answer": "（1）**先来先服务（FCFS）**：\n  顺序：P1(10)→P2(6)→P3(2)→P4(4)→P5(8)\n  周转时间：10, 16, 18, 22, 30\n  平均周转时间 = (10+16+18+22+30)/5 = 19.2\n\n"
            "（2）**时间片轮转（RR，q=2）**：\n  执行顺序：P1 P2 P3 P4 P5 P1 P2 P4 P5 P1 P5 P1 P1 P1\n  各进程完成时间：P1=28, P2=10, P3=4, P4=14, P5=24\n  周转时间：28, 10, 4, 14, 24\n  平均周转时间 = (28+10+4+14+24)/5 = 16.0\n\n"
            "（3）**优先权调度（非抢占，数值大优先级高）**：\n  顺序：P2(5)→P5(4)→P1(3)→P3(2)→P4(1)\n  周转时间：6, 6+8=14, 14+10=24, 26, 24+4=28\n  平均周转时间 = (6+14+24+26+28)/5 = 19.6\n\n"
            "计算结果：FCFS 平均周转时间 19.2，RR 16.0，优先权 19.6。",
            "explanation": "",
        },
        ("apply", 19): {
            "answer": "（1）**资源分配图**：\n```\n资源: R1(2) R2(2) R3(2) R4(1) R5(1)\n\nP1: 占有 R1×2, 申请 R2×1, R4×1\nP2: 占有 R2×1, 申请 R1×1\nP3: 占有 R2×1, 申请 R2×1, R3×1\nP4: 占有 R4×1, R5×1, 申请 R3×1\nP5: 占有 R3×1, 申请 R5×1\n\n分配后可用: R1=0, R2=0, R3=1, R4=0, R5=0\n```\n\n（2）**死锁定理**：如果资源分配图不可完全简化，则系统处于死锁状态。\n\n**判断过程**：\n- P3 需 R2(已无)和 R3(有1) → 阻塞\n- P5 需 R5(已无) → 阻塞\n- P1 需 R2(无)和 R4(无) → 阻塞\n- P2 需 R1(无) → 阻塞\n- P4 需 R3(有1) → 可分配，P4 完成释放 R4、R5\n- P4 释放后：R4=1, R5=1，但 P1 还需要 R2，P5 需要 R5 → 仅 P5 可运行\n- P5 运行释放 R3 → 但其他进程仍无法满足\n- **结果：存在死锁**，涉及 P1、P2、P3。",
            "explanation": "",
        },
        ("apply", 20): {
            "answer": "**并发性从大到小排序**：\n\n（1）**检测死锁 + 终止进程**（并发性最大）：不预先限制资源申请，允许最大并发，出现问题后检测并恢复。\n\n（2）**银行家算法**（并发性居中）：通过安全性检查预防死锁，有一定保守性，但可允许较高的资源利用率。\n\n（3）**资源预分配**（并发性最小）：进程运行前一次性申请全部所需资源，资源利用率低，并发度受严重限制。\n\n**排序**：检测死锁 > 银行家算法 > 资源预分配",
            "explanation": "",
        },
        ("apply", 26): {
            "answer": "内存 640KB，OS 占高端 40KB（600~640KB）。空闲区（初始）：[0, 600KB)。\n\n**首次适应算法**分配过程：\n```\n初始空闲区：[0, 600)\n①作业1(130)→[130, 600)\n②作业2(60)→[190, 600)\n③作业3(100)→[290, 600)\n④作业2释放→[190, 290), [290, 600)\n⑤作业4(200)→[190, 290)太小；从[290, 490)\n⑥作业3释放→[190, 290), [290, 490), [490, 600)合并→[190, 600)\n⑦作业1释放→[0,130), [190,600)合并→[0,600)\n⑧作业5(140)→[140, 600)\n⑨作业6(60)→[200, 600)\n⑩作业7(50)→[250, 600)\n⑪作业6释放→[200,250), [250,600)合并→[200,600)\n```\n最终空闲区（首次适应）：[0,140), [200,600)\n\n**最佳适应算法**略有不同，每次选最小的够用空闲区。\n\n（完整图请画出各步骤分区状态）",
            "explanation": "",
        },
        ("apply", 27): {
            "answer": "空闲区：F1(100K), F2(50K)。\n作业顺序：A(30K), B(70K), C(50K)。\n\n**最佳适应算法**：\n- A(30K)：F2(50K) 最接近 → 从 F2 分配，F2 剩余 20K\n- B(70K)：F1(100K) → 从 F1 分配，F1 剩余 30K\n- C(50K)：无足够空闲区 → 分配失败\n\n**最差适应算法**：\n- A(30K)：F1(100K) 最大 → 从 F1 分配，F1 剩余 70K\n- B(70K)：F1(70K) → 正好分配，F1 剩余 0\n- C(50K)：F2(50K) → 正好分配\n\n示意图：\n```\n最佳适应:  F1[30K空闲]  F2[20K空闲]  C分配失败\n最差适应:  F1[0]  F2[0]  → 全部成功\n```",
            "explanation": "",
        },
        # ── 应用题 — 虚拟存储/缺页/磁盘 ──────────────────────
        ("apply", 32): {
            "answer": "页面序列：4,3,2,1,4,3,5,4,3,2,1,5；物理块数 = 4，初始为空。\n\n**FIFO**：\n```\n  4 → [4]         缺页\n  3 → [4,3]       缺页\n  2 → [4,3,2]     缺页\n  1 → [4,3,2,1]   缺页\n  4 → [4,3,2,1]   命中\n  3 → [4,3,2,1]   命中\n  5 → [5,3,2,1]   缺页(淘汰4)\n  4 → [5,4,2,1]   缺页(淘汰3)\n  3 → [5,4,3,1]   缺页(淘汰2)\n  2 → [5,4,3,2]   缺页(淘汰1)\n  1 → [1,4,3,2]   缺页(淘汰5)\n  5 → [1,5,3,2]   缺页(淘汰4)\n```\n缺页次数：10，缺页率 = 10/12 ≈ 83.3%\n\n**LRU**：\n```\n  4 → [4]           缺页\n  3 → [4,3]         缺页\n  2 → [4,3,2]       缺页\n  1 → [4,3,2,1]     缺页\n  4 → [3,2,1,4]     命中\n  3 → [2,1,4,3]     命中\n  5 → [1,4,3,5]     缺页(淘汰2)\n  4 → [1,3,5,4]     命中\n  3 → [1,5,4,3]     命中\n  2 → [5,4,3,2]     缺页(淘汰1)\n  1 → [4,3,2,1]     缺页(淘汰5)\n  5 → [3,2,1,5]     缺页(淘汰4)\n```\n缺页次数：8，缺页率 = 8/12 ≈ 66.7%",
            "explanation": "",
        },
        ("apply", 33): {
            "answer": "CPU 20%，分页磁盘 97.7%，其他外设 5%。这说明系统**频繁缺页**（几乎满负荷进行磁盘交换），CPU 大量时间等待磁盘 I/O。\n\n分析各措施：\n\n**（1）更换速度更快的 CPU** ❌：不改善。CPU 利用率低是因为缺页频繁导致等待I/O，而非CPU速度不足。\n\n**（2）更换更大容量的分页磁盘** ❌：不改善。磁盘容量充足，瓶颈在于缺页率过高，而非磁盘容量。\n\n**（3）增加内存中用户进程数** ❌：反而恶化。更多进程会占用更多内存，进一步加剧缺页，磁盘 I/O 更繁忙。\n\n**（4）挂起内存中的某个（些）用户进程** ✅：有效。减少多道程序度，释放内存空间，降低缺页率，CPU 利用率会提升。",
            "explanation": "",
        },
        ("apply", 35): {
            "answer": "矩阵 100×100 = 10000 个整数，每页可存放 200 或 100 个整数。\n\n**每页 200 整数（每行占 0.5 页）**：\n- 程序 A（行优先 `A[i,j]`）：循环 i 在外层，每行访问连续 100 个元素（跨 1 页），共需 100 页\n  缺页次数 ≈ 100（每行一次缺页）\n- 程序 B（列优先 `A[j,i]`）：循环 j 在外层，访问跨行元素（每次跳 100 个整数，即每 2 页一次）\n  共 100×100 = 10000 次访问，每页 200 整数，每行约跨 0.5 页，每列跨 1 页\n  → 每次列访问 100 元素跨不同页，每页被访问 2 次后仍在内存？\n  → 精确：物理内存 2 页数据。B 按列访问，连续 100 个列元素占据 100 行 × 1 列，每行跨越不同页\n  缺页次数 ≈ 100×50 = 5000 次\n\n**每页 100 整数（每行占 1 页）**：\n- 程序 A：每行 100 整数 = 1 页，缺页次数 ≈ 100 次\n- 程序 B：每次访问不同页，缺页次数 ≈ 10000 次\n\n**说明的问题**：程序局部性对缺页率影响巨大。行优先访问利用空间局部性（同一页连续访问），缺页少；列优先访问破坏局部性（跨页跳跃），缺页极多。编写程序时应尽量按存储顺序访问数组。",
            "explanation": "",
        },
        ("apply", 39): {
            "answer": "当前磁头在 120 号柱面，刚刚完成 105 号柱面请求。请求队列：186, 158, 115, 90。\n\n**（1）先来先服务（FCFS）**：\n  次序：120→186→158→115→90\n  移动量：|186-120| + |158-186| + |115-158| + |90-115|\n       = 66 + 28 + 43 + 25 = 162\n\n**（2）最短查找时间优先（SSTF）**：\n  距 120 最近的请求：115(差5)，90(差30)，158(差38)，186(差66)\n  次序：120→115→90→158→186\n  移动量：5 + 25 + 68 + 28 = 126\n\n**（3）电梯调度（SCAN，向大号方向）**：\n  刚刚完成 105（减小方向），接下来应向增大的方向\n  次序：120→158→186→115→90\n  移动量：38 + 28 + 71 + 25 = 162",
            "explanation": "",
        },
        ("apply", 42): {
            "answer": "CSCAN（循环扫描），磁头在 100，方向增大。队列：50, 90, 30, 120。\n\n**调度次序**：先增大方向处理 ≥100 的请求：120；然后回到 0，继续增大：30→50→90。\n完整次序：100→120→0→30→50→90\n\n**寻道时间**：\n  100→120：20ms\n  120→199→0：|199-120| + 1 = 80ms（到最大号后回到 0）\n  0→30：30ms\n  30→50：20ms\n  50→90：40ms\n  总寻道时间 = 20 + 80 + 30 + 20 + 40 = 190ms\n\n**旋转延迟**：\n  转速 6000r/min = 100r/s，每转 10ms\n  平均旋转延迟 = 半圈 = 5ms/请求\n  5 个请求 × 5ms = 25ms\n\n**传输时间**：\n  每磁道 100 扇区，每转 10ms，每扇区传输 = 10/100 = 0.1ms\n  5 个扇区 × 0.1ms = 0.5ms\n\n**总时间** = 190 + 25 + 0.5 ≈ 215.5ms",
            "explanation": "",
        },
        ("apply", 43): {
            "answer": "矩阵 100×100 整数，以行为主存储。物理内存 3 页（1 页程序 + 2 页数据），每页容量 X 整数。\n\n**按行访问（外层 i，内层 j）**：\n  `for i := 1 to 100 do for j := 1 to 100 do A[i,j] := 0;`\n  每行 100 整数连续存放。若每页≥100 整数，每行只需 1 页，缺页 = 100 次。若每页=50 整数，每行跨 2 页，缺页 = 200 次。\n  利用空间局部性，性能好。\n\n**按列访问（外层 j，内层 i）**：\n  `for j := 1 to 100 do for i := 1 to 100 do A[i,j] := 0;`\n  每次访问跨越一行的距离（100 整数），若每页≤100，每访问 1 个元素可能触发 1 次缺页。\n  缺页 ≈ 10000 次。局部性差，性能极差。\n\n**结论**：按行存储的矩阵应尽量按行访问，充分利用空间局部性，减小缺页率。",
            "explanation": "",
        },
        # ── 应用题 — 文件系统 ──────────────────────────────────
        ("apply", 49): {
            "answer": "块大小 = 512 字节，块号 = 3 字节，每块可存放块号数 = 512/3 ≈ 170（取整）。\n\n**直接寻址（10 块）**：\n  最大文件 = 10 × 512 = 5KB\n\n**一级索引**：\n  一个索引块含 170 个块号 → 170 × 512 = 85KB\n\n**二级索引**：\n  一级索引块指向 170 个二级索引块，每个二级索引块指向 170 个数据块\n  → 170 × 170 × 512 = 170² × 512 = 28900 × 512 ≈ 14.45MB\n\n**三级索引**：\n  → 170 × 170 × 170 × 512 = 170³ × 512 ≈ 4.91M × 512 ≈ 2.46GB\n\n结果：\n- 二级索引最大文件 ≈ 14.45 MB\n- 三级索引最大文件 ≈ 2.46 GB",
            "explanation": "",
        },
        ("apply", 50): {
            "answer": "UNIX 文件系统采用多级索引结构（i 节点）。\n\n**（a）文件不超过 10 块**：\n```\ni节点: [直接0][直接1]...[直接9]\n         ↓        ↓        ↓\n       数据块   数据块   数据块\n```\n全部使用直接地址，通过 i 节点中 10 个直接指针直接访问。\n\n**（b）文件在 11~256 块之间**：\n```\ni节点: [直接0..9][一次间接]\n                    ↓\n                 索引块 [块号0..块号n]\n                    ↓ ↓       ↓\n                 数据块 数据块  数据块\n```\n前 10 块通过直接指针访问，剩余块通过一次间接索引（索引块存块号）。\n\n**（c）文件超过 256 块**：\n```\ni节点: [直接0..9][一次间接][二次间接]\n                              ↓\n                           一级索引块\n                      ↓   ↓       ↓\n                   二级索引块 二级索引块 ...\n                 ↓  ↓       ↓\n               数据块 数据块  数据块\n```\n启用二次间接索引，两级索引可访问大量数据块。",
            "explanation": "",
        },
        # ── 算法设计题 — P/V 操作 ─────────────────────────────
        ("algo", 1): {
            "answer": "```\nsemaphore empty = 1;   // 盘子是否为空\nsemaphore apple = 0;   // 盘中有苹果\nsemaphore orange = 0;  // 盘中有桔子\n\n// 爸爸：放苹果\nvoid father() {\n    while (true) {\n        P(empty);\n        放入苹果;\n        V(apple);\n    }\n}\n\n// 妈妈：放桔子\nvoid mother() {\n    while (true) {\n        P(empty);\n        放入桔子;\n        V(orange);\n    }\n}\n\n// 儿子：取桔子\nvoid son() {\n    while (true) {\n        P(orange);\n        取出桔子;\n        V(empty);\n        享用桔子;\n    }\n}\n\n// 女儿：取苹果\nvoid daughter() {\n    while (true) {\n        P(apple);\n        取出苹果;\n        V(empty);\n        享用苹果;\n    }\n}\n\n``\n\n信号量初始值：empty=1（盘子为空），apple=0（暂无苹果），orange=0（暂无桔子）。",
            "explanation": "",
        },
        ("algo", 2): {
            "answer": "```\nsemaphore s_start = 0;  // 启动信号\nsemaphore s_stop = 0;   // 停车信号\n\n// 司机\nvoid driver() {\n    while (true) {\n        P(s_start);         // 等待关门\n        启动车辆;\n        正常行车;\n        到站停车;\n        V(s_stop);          // 通知开门\n    }\n}\n\n// 售票员\nvoid conductor() {\n    while (true) {\n        关车门;\n        V(s_start);         // 允许启动\n        售票;\n        P(s_stop);          // 等待停车\n        开车门;\n        乘客上下车;\n    }\n}\n```\n\n使用两个信号量实现司机和售票员的单向同步：关门→启动→到站→开门→关门……",
            "explanation": "",
        },
        ("algo", 3): {
            "answer": "```\nsemaphore mutex = 1;  // 路口互斥，每次只允许一辆车通过\n\n// 东向西\nvoid east_west() {\n    while (true) {\n        P(mutex);\n        从东向西通过路口;\n        V(mutex);\n    }\n}\n\n// 南向北\nvoid south_north() {\n    while (true) {\n        P(mutex);\n        从南向北通过路口;\n        V(mutex);\n    }\n}\n```\n\n由于路口每次只允许一辆车通行（不论方向），用一个互斥信号量即可实现。东向西和南向北的车辆竞争同一路口资源。",
            "explanation": "",
        },
        ("algo", 4): {
            "answer": "（1）**A、B 进程的相互制约关系**：\n- **互斥关系**：A、B 进程不能同时访问缓冲区\n- **同步关系**：A 进程写入前缓冲区必须有空位（空→满），B 进程读出前缓冲区必须有数据（满→空）\n\n（2）**P、V 操作算法**：\n```\n#define N 100\nsemaphore empty = N;  // 空缓冲区数\nsemaphore full = 0;   // 满缓冲区数\nsemaphore mutex = 1;  // 互斥\nint in = 0, out = 0;\n\n// A 进程（生产者）\nvoid process_A() {\n    while (true) {\n        准备信息;\n        P(empty);\n        P(mutex);\n        buffer[in] = 信息;\n        in = (in + 1) % N;\n        V(mutex);\n        V(full);\n    }\n}\n\n// B 进程（消费者）\nvoid process_B() {\n    while (true) {\n        P(full);\n        P(mutex);\n        信息 = buffer[out];\n        out = (out + 1) % N;\n        V(mutex);\n        V(empty);\n        处理信息;\n    }\n}\n```",
            "explanation": "",
        },
        ("algo", 5): {
            "answer": "```\nsemaphore SA = 0;  // A 完成\nsemaphore SB = 0;  // B 完成\nsemaphore SC = 0;  // C 完成（前驱A和B）\nsemaphore SD = 0;  // D 完成\n\nA() { 执行A; V(SA); }\nB() { 执行B; V(SB); }\nC() { P(SA); P(SB); 执行C; V(SC); }\nD() { 执行D; V(SD); }\nE() { P(SC); P(SD); 执行E; }\n```\n\n信号量初值均为 0。C 必须等待 A 和 B 都完成才能执行；E 必须等待 C 和 D 都完成才能执行。",
            "explanation": "",
        },
        ("algo", 6): {
            "answer": "```\n#define N 5\nsemaphore chopstick[N];\nfor (int i = 0; i < N; i++) chopstick[i] = 1;\nsemaphore mutex = N - 1;  // 最多 N-1 位哲学家同时就餐\n\nvoid philosopher(int i) {\n    while (true) {\n        思考;\n        P(mutex);               // 限制并发数\n        P(chopstick[i]);        // 取左筷\n        P(chopstick[(i+1)%N]);  // 取右筷\n        就餐;\n        V(chopstick[i]);\n        V(chopstick[(i+1)%N]);\n        V(mutex);\n    }\n}\n```\n\n**预防死锁**：通过 mutex 限制同时就餐人数 ≤ N-1，确保至少有一人可拿到两根筷子，破坏循环等待条件。",
            "explanation": "",
        },
        ("algo", 7): {
            "answer": "```\nsemaphore empty1 = 1;  // 缓冲区1是否为空\nsemaphore full1 = 0;   // 缓冲区1是否有数据\nsemaphore empty2 = 1;  // 缓冲区2是否为空\nsemaphore full2 = 0;   // 缓冲区2是否有数据\n\n// P1：磁盘→缓冲区1\nvoid P1() {\n    while (true) {\n        从磁盘读一个记录到缓冲区1;\n        V(full1);\n        P(empty1);\n    }\n}\n\n// P2：缓冲区1→缓冲区2\nvoid P2() {\n    while (true) {\n        P(full1);\n        从缓冲区1复制到缓冲区2;\n        V(empty1);\n        V(full2);\n        P(empty2);\n    }\n}\n\n// P3：缓冲区2→打印\nvoid P3() {\n    while (true) {\n        P(full2);\n        打印缓冲区2中的记录;\n        V(empty2);\n    }\n}\n```\n\n信号量初始值：empty1=1, full1=0, empty2=1, full2=0，构成两对生产-消费关系。",
            "explanation": "",
        },
        ("algo", 8): {
            "answer": "```\nsemaphore empty = 2000;   // 展馆空位\nsemaphore mutex = 1;      // 出入口互斥\nint x = 0;                // 普通票人数\nint y = 0;                // 学生票人数\nsemaphore diff = 400;     // 控制 0 ≤ x-y ≤ 400\n\n// 普通票进入\nvoid enter_regular() {\n    P(empty);\n    P(mutex);\n    x++;\n    V(mutex);\n    P(diff);               // 维护差值上限\n    进入;\n}\n\n// 普通票离开\nvoid leave_regular() {\n    P(mutex);\n    x--;\n    V(diff);\n    V(mutex);\n    V(empty);\n}\n\n// 学生票进入\nvoid enter_student() {\n    P(empty);\n    P(mutex);\n    y++;\n    V(diff);               // 学生+1 缩小差值\n    V(mutex);\n    进入;\n}\n\n// 学生票离开\nvoid leave_student() {\n    P(mutex);\n    y--;\n    V(mutex);\n    V(empty);\n}\n```",
            "explanation": "",
        },
        ("algo", 9): {
            "answer": "```\nsemaphore mutex = 1;       // 路口互斥\nsemaphore ped_pass = 0;    // 行人通过信号\nint waiting = 0;           // 等待的行人数\n\n// 行人\nvoid pedestrian() {\n    while (true) {\n        P(mutex);\n        waiting++;\n        V(ped_pass);\n        V(mutex);\n        通过路口;\n        P(mutex);\n        waiting--;\n        V(mutex);\n    }\n}\n\n// 机动车\nvoid vehicle() {\n    while (true) {\n        P(mutex);\n        while (waiting > 0) {\n            V(mutex);\n            P(ped_pass);    // 让行人先通过\n            P(mutex);\n        }\n        通过路口;\n        V(mutex);\n    }\n}\n```\n\n行人和机动车互斥占用路口，行人优先通行（机动车等待所有行人通过后方可通过）。",
            "explanation": "",
        },
        ("algo", 10): {
            "answer": "```\nsemaphore empty = 1000;   // 缓冲区空位\nsemaphore full = 0;       // 产品数\nsemaphore mutex = 1;      // 缓冲区互斥\nsemaphore block = 1;      // 连续取10件的互斥\n\nvoid producer() {\n    while (true) {\n        生产一件产品;\n        P(empty);\n        P(mutex);\n        放入产品;\n        V(mutex);\n        V(full);\n    }\n}\n\nvoid consumer() {\n    while (true) {\n        P(block);              // 获得连续取10件的资格\n        for (int i = 0; i < 10; i++) {\n            P(full);\n            P(mutex);\n            取出一件产品;\n            V(mutex);\n            V(empty);\n        }\n        V(block);              // 其他消费者可开始取\n    }\n}\n```\n\n信号量含义：empty—缓冲区空位数（初值1000）；full—已存产品数（初值0）；mutex—缓冲区互斥（初值1）；block—连续取操作互斥（初值1）。",
            "explanation": "",
        },
        ("algo", 11): {
            "answer": "```\nsemaphore S12 = 0;     // P1 → P2 信号\nsemaphore S13 = 0;     // P1 → P3 信号\nsemaphore S24 = 0;     // P2 → P4 信号\nsemaphore S34 = 0;     // P3 → P4 信号\nsemaphore mutex = 1;   // P2 与 P3 互斥\n\nvoid P1() {\n    执行P1任务;\n    V(S12);\n    V(S13);\n}\n\nvoid P2() {\n    P(mutex);\n    P(S12);             // 等待P1完成\n    执行P2任务;\n    V(S24);\n    V(mutex);\n}\n\nvoid P3() {\n    P(mutex);\n    P(S13);             // 等待P1完成\n    执行P3任务;\n    V(S34);\n    V(mutex);\n}\n\nvoid P4() {\n    P(S24);             // 等待P2完成\n    P(S34);             // 等待P3完成\n    执行P4任务;\n}\n```\n\nmutex 确保 P2 和 P3 互斥执行；信号量 S12/S13 保证 P1 先于 P2/P3 完成；S24/S34 保证 P2/P3 先于 P4 完成。",
            "explanation": "",
        },
        ("algo", 12): {
            "answer": "根据题目给出的前驱图（具体拓扑连接以试卷为准），假设通用依赖关系为：P1 → P2,P3 → P4 → P5,P6\n```\nsemaphore S12 = 0, S13 = 0;\nsemaphore S24 = 0, S34 = 0;\nsemaphore S45 = 0, S46 = 0;\n\nvoid P1() { 执行; V(S12); V(S13); }\nvoid P2() { P(S12); 执行; V(S24); }\nvoid P3() { P(S13); 执行; V(S34); }\nvoid P4() { P(S24); P(S34); 执行; V(S45); V(S46); }\nvoid P5() { P(S45); 执行; }\nvoid P6() { P(S46); 执行; }\n```\n\n若前驱图不同，根据实际依赖关系增加或调整信号量数量。",
            "explanation": "",
        },
        ("algo", 13): {
            "answer": "**导致死锁的执行次序**：\nP1 申请 R1（P(M1)），P2 申请 R2（P(M2)），然后 P1 申请 R2（P(M2)）阻塞，P2 申请 R1（P(M1)）阻塞，形成循环等待。\n\n**修改算法（按序分配，避免循环等待）**：\n```\nsemaphore M1 = 1;  // R1 互斥\nsemaphore M2 = 1;  // R2 互斥\n\n// P1\nvoid P1() {\n    P(M1);           // 申请 R1\n    P(M2);           // 申请 R2\n    使用 R1 和 R2;\n    V(M2);\n    V(M1);\n}\n\n// P2（按相同顺序申请）\nvoid P2() {\n    P(M1);           // 先申请 R1，后申请 R2\n    P(M2);\n    使用 R1 和 R2;\n    V(M2);\n    V(M1);\n}\n```\n\n**原理**：按相同顺序（R1→R2）申请资源，破坏循环等待条件，预防死锁。",
            "explanation": "",
        },
        ("algo", 14): {
            "answer": "```\n#define N 5  // 哲学家数\nsemaphore chopstick[N];\nfor (int i = 0; i < N; i++) chopstick[i] = 1;\nsemaphore bowl = m;     // 碗资源\n\nvoid philosopher(int i) {\n    while (true) {\n        思考;\n        P(bowl);                // 取碗\n        P(chopstick[i]);        // 取左筷\n        P(chopstick[(i+1)%N]);  // 取右筷\n        就餐;\n        V(chopstick[i]);\n        V(chopstick[(i+1)%N]);\n        V(bowl);\n    }\n}\n```\n\n碗的数量 m 起到限制同时就餐人数的效果。当 m < N 时，至少有一位哲学家无法取到碗，从而防止所有哲学家同时拿起一根筷子而导致的死锁。",
            "explanation": "",
        },
        ("algo", 15): {
            "answer": "参考前驱图（以具体题目图示为准），假设如下连接关系：\nP1 完成后 P2、P3 开始；P2、P3 完成后 P4 开始；P4 完成后 P5、P6 开始。\n```\nsemaphore S12 = 0, S13 = 0;  // P1→P2, P1→P3\nsemaphore S24 = 0, S34 = 0;  // P2→P4, P3→P4\nsemaphore S45 = 0, S46 = 0;  // P4→P5, P4→P6\n\nP1() { 执行; V(S12); V(S13); }\nP2() { P(S12); 执行; V(S24); }\nP3() { P(S13); 执行; V(S34); }\nP4() { P(S24); P(S34); 执行; V(S45); V(S46); }\nP5() { P(S45); 执行; }\nP6() { P(S46); 执行; }\n```\n\n若图中存在并发控制需求，增加互斥信号量。",
            "explanation": "",
        },
        ("algo", 16): {
            "answer": "**死锁发生的执行次序**：\nP1: P(M1) → 占有R1, 然后 P(M2) → 等待R2\nP2: P(M2) → 占有R2, 然后 P(M1) → 等待R1\n两者互相等待，形成死锁。\n\n**修改算法（按序分配资源）**：\n```\nsemaphore M1 = 1;\nsemaphore M2 = 1;\n\n// P1\nP1() {\n    P(M1);   // 申请 R1\n    P(M2);   // 申请 R2\n    使用 R1、R2;\n    V(M2);\n    V(M1);\n}\n\n// P2（与 P1 保持相同申请顺序）\nP2() {\n    P(M1);   // 先 R1\n    P(M2);   // 后 R2\n    使用 R1、R2;\n    V(M2);\n    V(M1);\n}\n```\n\nP2 改为先申请 R1 再申请 R2，与 P1 的顺序一致，破坏循环等待。",
            "explanation": "",
        },
        ("algo", 17): {
            "answer": "```\n#define N 5\nsemaphore chopstick[N];\nfor (int i = 0; i < N; i++) chopstick[i] = 1;\nsemaphore bowl = m;     // 中心碗数 m\nsemaphore mutex = 1;    // 操作计数互斥\n\nvoid philosopher(int i) {\n    while (true) {\n        思考;\n        P(bowl);                // 先取碗（限制并发数）\n        P(chopstick[i]);        // 取左筷\n        P(chopstick[(i+1)%N]);  // 取右筷\n        就餐;\n        V(chopstick[i]);\n        V(chopstick[(i+1)%N]);\n        V(bowl);                // 放回碗\n    }\n}\n```\n\n当 m ≥ N 时，碗不成为瓶颈，需额外限制（如用计数器限制最多 N-1 人同时就餐）。\n当 m < N 时，同时就餐人数 ≤ m，直接通过碗数量预防死锁，且 m 越大并发度越高。",
            "explanation": "",
        },
    }
    for key, val in missing.items():
        if key not in answers:
            answers[key] = val
    return answers


# ─── 主流程 ──────────────────────────────────────────────────────


def main():
    print("解析题库...")
    questions = parse_questions()
    print(f"  题库提取 {len(questions)} 道题")

    print("解析答案...")
    answers = parse_answers()
    print(f"  答案提取 {len(answers)} 条")

    # ─── 补全原始答案文件中缺少的 40 道题答案 ─────────────────────
    answers = fill_missing_answers(answers)

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
        # 为无答案题目添加占位标记
        if not q.get("answer"):
            type_hints = {
                "algo": "（算法设计题，请参考教材相关章节）",
                "apply": "（本题暂无参考答案）",
                "short": "（本题暂无参考答案）",
            }
            q["answer"] = type_hints.get(q["type"], "")

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
