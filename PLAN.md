# 轻量化操作系统测验系统 — 项目规划

> 基于《操作系统复习题集》与《操作系统参考答案》构建的轻量 Web 测验系统。

---

## 一、项目概述

### 1.1 目标

将现有 Markdown 题集与参考答案解析为一套结构化题库，提供**分类练习**、**组卷测验**、**错题练习**三大功能，帮助用户高效备考。

### 1.2 技术选型

| 层 | 选型 | 理由 |
|:---|:---|:---|
| 数据解析 | Python 3 | 文本处理能力强，Miniforge3 环境可用 |
| 前端 | 原生 HTML5 + CSS3 + ES6 | 零框架、零构建、开箱即用 |
| 数据存储 | `questions.json`（静态）| 一次性生成，前端 fetch 加载 |
| 用户状态 | `localStorage` | 错题记录、答题进度、测验历史持久化 |
| 本地服务 | `python -m http.server` | 开发与使用均无需安装任何依赖 |

### 1.3 核心约定

- 题集文件：`操作系统复习题集.md`
- 答案文件：`操作系统参考答案.md`
- 输出数据：`questions.json`
- 前端入口：`index.html`
- 启动脚本：`start.bat`

---

## 二、题库解析（`parse_questions.py`）

### 2.1 输入输出

```
操作系统复习题集.md  ─┐
                       ├─→ parse_questions.py → questions.json
操作系统参考答案.md  ─┘
```

### 2.2 解析策略

按题型分阶段解析，每个题型内部按章节分割：

1. **选择题**（219 题）— 行首数字匹配题号，后续行提取选项 A/B/C/D
2. **填空题**（85 题）— 统计 `______` 数量作为 `blankCount`，支持多空
3. **判断题**（81 题）— 行首数字匹配题号，答案从参考答案匹配
4. **简答题**（71 题）— 支持多行子问题（`（1）`、`（2）`）
5. **应用题**（60 题）— 表格检测与结构化解析
6. **算法设计题**（17 题）— 纳入题库仅用于分类练习

### 2.3 表格解析（核心功能）

逐行扫描，连续符合 `^|.*|$` 模式的行构成一个表格块：

```
检测到表头行    → headers
检测到分隔行    → align 数组（:---  = left, :---: = center, ---: = right）
检测到数据行    → rows 数组
连续空行终止    → 关闭表格块
```

每个表格独立解析为结构化对象并入 `blocks`。

### 2.4 答案关联

- 题号配对：`（题型, 章节, 题号）` 三元组匹配题集与答案
- 选择题自动对应 A/B/C/D
- 填空题答案按 `_____` 位置拆分为数组
- 判断题映射为 `正确 / 错误`
- 简答/应用题保留答案为 Markdown 文本

### 2.5 每条题目的 JSON 结构

```json
{
  "id": "choice-1",
  "type": "choice",
  "chapter": 1,
  "chapterName": "操作系统引论",
  "number": 1,
  "questionMD": "从用户的观点看，操作系统是（ ）。\n\nA. 用户与计算机...\nB. 控制和管理...\nC. 合理地组织...\nD. 由若干层次的...",

  "blocks": [
    { "type": "text", "content": "从用户的观点看，操作系统是（ ）。" },
    { "type": "options", "options": [
        "A. 用户与计算机硬件之间的接口",
        "B. 控制和管理计算机资源的软件",
        "C. 合理地组织计算机工作流程的软件",
        "D. 由若干层次的程序按一定的结构组成的有机体"
    ]}
  ],

  "answer": "A",
  "explanation": "操作系统是用户与计算机硬件系统之间的接口。",

  "tags": ["concept"],
  "blankCount": 0
}

```

#### 题型特有字段

| 题型 | 特有字段 |
|:---|:---|
| choice | `options: string[]` |
| fill | `blankCount: number`，`answer: string[]` |
| judge | — |
| short | — |
| apply | `blocks` 中可能含 `type: "table"` |
| algo | — |

#### 表格块结构

```json
{
  "type": "table",
  "headers": ["作业号", "进入时刻", "估计运行时间"],
  "align": ["center", "center", "center"],
  "rows": [
    ["1", "10:00", "30 分钟"],
    ["2", "10:10", "40 分钟"],
    ["3", "10:20", "20 分钟"],
    ["4", "11:00", "15 分钟"],
    ["5", "11:30", "10 分钟"]
  ]
}
```

---

## 三、前端架构（`index.html`）

### 3.1 路由与状态

采用简单状态机驱动视图切换：

```javascript
const state = {
  page: 'practice',        // practice | exam | wrong
  chapter: 1,              // 1-8, 0 = all
  type: 'all',             // all | choice | fill | judge | short | apply | algo
  data: null,              // questions.json 解析结果
  progress: {},            // localStorage 进度
  wrongQuestions: {}       // localStorage 错题
}
```

页面切换时无需 URL hash，全部 DOM 内联渲染。

### 3.2 界面结构

```
┌─────────────────────────────────────────────────┐
│  🖥  OS 测验系统                                  │
│  [分类练习]  [组卷测验]  [错题本]                   │
├─────────────────────────────────────────────────┤
│  [第1章] [第2章] [第3章] ... [第8章]  题型过滤     │
│  ┌─────────────────────────────────────────────┐│
│  │  题目卡片                                    ││
│  │  ─────────────────────────────────────────  ││
│  │  blocks 渲染区域（文本段落 + 表格 + 选项）    ││
│  │  ─────────────────────────────────────────  ││
│  │  作答区域 / 答案显示 / 解析                   ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### 3.3 Blocks 渲染器

```javascript
function renderBlocks(blocks, container) {
  for (const block of blocks) {
    switch (block.type) {
      case 'text':
        container.append(renderText(block.content))
        break
      case 'options':
        container.append(renderOptions(block.options))
        break
      case 'table':
        container.append(renderTable(block))
        break
    }
  }
}

function renderTable(block) {
  const table = document.createElement('table')
  table.className = 'quiz-table'
  // thead from block.headers
  // tbody from block.rows
  // col align from block.align
  return table
}
```

### 3.4 填空题输入

- 根据 `blankCount` 动态生成 N 个 `<input>`，按顺序对应答案数组
- 空格周围文本保留在 `<p>` 中，`______` 替换为 `<input>`
- 批改时逐空比对，支持全半角容错

---

## 四、三大功能详细设计

### 4.1 分类练习

- **章节筛选**：Tab 切换 1~8 章 + "全部"
- **题型筛选**：按钮过滤 `choice / fill / judge / short / apply / algo`
- **交互流程**：
  1. 显示题目 → 用户作答 → 点击「确认」
  2. 选择题点击选项按钮即选中
  3. 填空题输入后点击确认
  4. 显示正确/错误标记 + 解析
  5. 答错自动入错题本
- **进度条**：章节 Tab 下方显示 `已答 X / 共 Y 题，正确率 Z%`

### 4.2 组卷测验

#### 4.2.1 出卷参数

| 参数 | 默认值 | 说明 |
|:---|:---:|:---|
| 限时 | 不限时 | 120 分钟 / 不限时 |
| 试卷数 | 1 | 可生成多套不同试卷 |
| 包含章节 | 全部 | 可选排除已掌握章节 |

#### 4.2.2 分层抽样算法

```
function generatePaper(questions, options):
  paper = { parts: [], totalScore: 0 }
  
  // ① 选择题 20 题 × 1 分 = 20 分
  choiceBuckets = distributeByChapter(questions.choice, [2,3,3,3,2,2,3,2])
  paper.parts.push({type:'choice', questions: sampleEach(choiceBuckets), maxScore:20})
  
  // ② 填空题 10 空 × 1 分 = 10 分
  fillPool = shuffle(questions.fill)
  selected = []; blanks = 0
  for q in fillPool:
    if blanks + q.blankCount <= 10:
      selected.push(q); blanks += q.blankCount
    if blanks == 10: break
  paper.parts.push({type:'fill', questions: selected, maxScore:10})
  
  // ③ 简答题 5 题 × 6 分 = 30 分
  shortSelected = pickAcrossChapters(questions.short, 5)
  paper.parts.push({type:'short', questions: shortSelected, maxScore:30})
  
  // ④ 应用题 5 题 × 8 分 = 40 分
  applySelected = pickAcrossChapters(questions.apply, 5)
  paper.parts.push({type:'apply', questions: applySelected, maxScore:40})
  
  return paper  // totalScore = 100
```

#### 4.2.3 答题流程

1. 用户点击「生成新试卷」→ 显示试卷概览（题型分布、章节覆盖度）
2. 点击「开始作答」→ 切换为测验界面，倒计时启动（如限时）
3. 选择题逐题作答，填空题逐空填写，简答/应用用 `<textarea>`
4. 答题过程中自动保存至 sessionStorage（防刷新丢失）
5. 交卷方式：手动点击「交卷」或倒计时归零自动交卷

#### 4.2.4 批改与成绩报告

| 题型 | 批改方式 | 说明 |
|:---|:---|:---|
| 选择题 | 全自动 | 比对 A/B/C/D |
| 填空题 | 全自动 | 逐空比对，全半角容错 |
| 判断题 | 全自动 | 比对"正确/错误" |
| 简答题 | 用户自评 | 显示参考答案，用户手动打分 |
| 应用题 | 用户自评 | 显示参考答案 + 推导，用户手动打分 |

成绩报告：
- 总分、各题型得分、正确率
- 每题答题情况（正确/错误/未作答）
- 错题自动追加到错题本
- 可点击「查看解析」回顾每道题

#### 4.2.5 限时模式

- 默认 120 分钟倒计时
- 顶部导航栏实时显示 `⏱ 剩余时间：01:45:32`
- 剩余 5 分钟时弹窗提醒
- 倒计时归零自动交卷，已答部分批改，未答计 0 分
- 提供「隐藏计时」选项（心理暗示）

### 4.3 错题练习

#### 4.3.1 数据存储

```javascript
// localStorage 结构
{
  "wrongQuestions": {
    "choice-1":  { count: 2, userAnswer: "B", lastWrong: "2026-06-13" },
    "fill-40":   { count: 1, userAnswer: ["56C5"], lastWrong: "2026-06-12" },
    "apply-13":  { count: 3, userAnswer: "55 分钟", lastWrong: "2026-06-10" }
  },
  "examHistory": [
    { date: "2026-06-13", score: 82, total: 100, details: [...] },
    ...
  ]
}
```

#### 4.3.2 功能界面

- 按章节 / 题型筛选错题
- 每条显示：题目、上一次错误答案、错误次数
- 点击「重做」进入单题模式
- 连续 2 次答对自动标记「已掌握」，可手动移出
- 批量操作：「全部重做」「清空已掌握」「清空全部」

#### 4.3.3 导出 MD

按钮「导出错题 MD」触发下载：

```markdown
# 错题集

> 导出时间：2026-06-13 14:30
> 共计 15 题（选择题 6，填空题 3，判断题 2，简答题 2，应用题 2）

---

## 第 1 章 操作系统引论

### 选择题

**1. 从用户的观点看，操作系统是（ ）。**
- A. 用户与计算机硬件之间的接口
- B. 控制和管理计算机资源的软件
- C. 合理地组织计算机工作流程的软件
- D. 由若干层次的程序按一定的结构组成的有机体

**你的答案：** B  
**正确答案：** A  
**解析：** 操作系统是用户与计算机硬件系统之间的接口。  
**错误次数：** 2

---
```

- 按章节分组，同一章节内按题型排序
- 导出内容使用 `questionMD` 原始 Markdown，表格完整保留
- 文件命名：`错题集_2026-06-13.md`

---

## 五、样式规范

### 5.1 设计原则

- 简洁、清晰、低视觉负担
- 突出题目与作答区域，弱化导航装饰

### 5.2 配色

| 角色 | 色值 | 用途 |
|:---|:---:|:---|
| 背景 | `#f5f7fa` | 页面底色 |
| 卡片 | `#ffffff` | 题目容器 |
| 主色 | `#3b82f6` | Tab 激活、按钮 |
| 正确 | `#22c55e` | ✅ 标记 |
| 错误 | `#ef4444` | ❌ 标记 |
| 文本 | `#1e293b` | 正文 |
| 次要 | `#64748b` | 辅助说明 |

### 5.3 表格主题

```css
.quiz-table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75em 0;
  font-size: 0.9em;
}
.quiz-table th,
.quiz-table td {
  border: 1px solid #cbd5e1;
  padding: 6px 12px;
  text-align: center;
}
.quiz-table thead {
  background: #f1f5f9;
  font-weight: 600;
}
```

### 5.4 响应式

- 桌面：卡片 720px 居中
- 平板（<768px）：卡片 96% 宽度
- 手机（<480px）：表格横向滚动支持

---

## 六、实现路线

### Step 1：题库解析脚本

- 文件：`parse_questions.py`
- 实现选择题、填空题、判断题、简答题、应用题、算法设计题的解析
- 实现表格块检测与结构化解析
- 实现答案文件关联匹配
- 输出 `questions.json` 并打印统计信息

### Step 2：前端骨架

- `index.html` 核心 DOM 结构
- 数据加载（fetch questions.json）
- 路由状态机（三页切换）
- 章节 Tab + 题型过滤

### Step 3：分类练习

- blocks 渲染器（text / options / table）
- 作答交互（点击选项、填空输入）
- 判题 + 显示解析
- 章节进度跟踪

### Step 4：组卷测验

- 分层抽样算法
- 测验界面（限时/不限时）
- 自动批改（选择/填空/判断）
- 成绩报告 + 错题本追加

### Step 5：错题练习

- localStorage 读写封装
- 错题列表 + 筛选
- 重做 + 已掌握标记
- 导出 MD 功能

### Step 6：打磨

- 填空题容错（全半角、首尾空格）
- 限时倒计时提醒
- 简答/应用题自评界面
- 响应式适配
- `start.bat` 脚本

---

## 七、进度跟踪

### 7.1 里程碑

| 里程碑 | 预计产出 | 前置依赖 |
|:---|:---|:---|
| M1 解析完成 | `questions.json` 数据文件 | — |
| M2 骨架完成 | `index.html` 三页切换 + 数据加载 | M1 |
| M3 分类练习可用 | 章节/题型筛选 + 作答判题 | M2 |
| M4 组卷测验可用 | 出卷 + 答题 + 批改 + 成绩报告 | M3 |
| M5 错题练习可用 | 错题本 + 导出 MD | M4 |
| M6 发布 | 全部功能验收 + 样式打磨 | M5 |

### 7.2 已完成

- [x] 题库结构分析（533 题，6 题型，8 章节）
- [x] 参考答案验证与修正（5 处错误已修复）
- [x] 18 道计算填空题推导补充
- [x] 项目规划文档（本文件）

### 7.3 待办

- [ ] Step 1：`parse_questions.py`
- [ ] Step 2：前端骨架
- [ ] Step 3：分类练习
- [ ] Step 4：组卷测验
- [ ] Step 5：错题练习
- [ ] Step 6：打磨发布

---

## 八、附录

### 8.1 题库统计

| 题型 | 数量 | 涉及章节 |
|:---|:---:|:---|
| 选择题 | 219 | 1-8 |
| 填空题 | 85 | 1-8 |
| 判断题 | 81 | 1-5, 7-8 |
| 简答题 | 71 | 1-8 |
| 应用题 | 60 | 3-8 |
| 算法设计题 | 17 | 3 |
| **合计** | **533** | |

### 8.2 组卷分数分布

| 题型 | 题量 | 单题分值 | 小计 |
|:---|:---:|:---:|:---:|
| 选择题 | 20 | 1 | 20 |
| 填空题 | 10 空 | 1 | 10 |
| 简答题 | 5 | 6 | 30 |
| 应用题 | 5 | 8 | 40 |
| **总分** | **40** | | **100** |

### 8.3 参考来源

- 《操作系统复习题集.md》— 原始题集
- 《操作系统参考答案.md》— 修正后参考答案
