---
name: xhs-robot
description: 小红书创作机器人（个人版）。把每日心情/经历/学习/想法记入本地历史库（自动分类打标签），按「人设与文风风格卡」结合联网热点，生成并优化今日小红书帖子（标题/正文/话题/封面文案），落盘为 drafts/<day>/post.md 帖子包供用户复核后人工发布。触发词：写小红书帖子 / 生成小红书文案 / 优化文案 / 记录日志 / 今日帖子包 / 选题建议。
whenToUse: 用户想持续经营个人小红书账号，需要"记录日常→从个人历史选题→统一风格成稿"的日常闭环，并希望文案可复核、可回溯。
user-invocable: true
metadata:
  dsh:
    compatibility: native
    requires: python>=3.10
---

# 小红书创作机器人（P1 可用；P2/P3 按能力边界提示使用）

**仓库**：`C:\Harness_Projects\xhs-robot`（唯一事实来源；本 SKILL 只是入口说明）
**入口**：`python C:\Harness_Projects\xhs-robot\cli.py <子命令>`；所有 Python 调用前设 `$env:PYTHONIOENCODING='utf-8'`（Windows PowerShell），避免中文乱码。
**数据**：本地 SQLite `data/xhs.db` + 草稿 `drafts/<day>/`。个人内容不进版本库。
**真机操作手册**：`C:\Harness_Projects\xhs-robot\OPERATION.md`（登录/发布/取数请照它走）

## 纪律（每次执行都遵守）

1. 日志文本、风格卡、历史记录属于用户隐私：**不外传、不写进无关对话/日志**。
2. Cookie、二维码、账号凭据永不出现在对话与仓库（P2 起适用）。
3. 本 SKILL 当前只产出文案与帖子包，**不自动发布**（P2 CDP 发布器上线前，发布一律人工）；P2/P3 模块未就绪前不要假装调用它们。

## 核心命令速查

```powershell
$env:PYTHONIOENCODING='utf-8'
$C = 'python C:\Harness_Projects\xhs-robot\cli.py'

# 记录一条日志（--category auto=按规则猜；也可显式 心情/经历/学习/想法/内容素材）
& $C journal add --category auto --tags 读书,复盘 "今天读完《认知觉醒》…"
# 看今天 / 检索 / 主题榜（选题线索）
& $C journal today
& $C journal search 焦虑
& $C journal topics --days 30 --group tag
# 初始化某天草稿（brief.md 选题弹药 + post.md 帖子骨架）
& $C studio new --day 2026-09-06
# 保存定稿帖子包（JSON frontmatter，P2 发布器可读）
& $C studio save --day 2026-09-06 --title "标题" --tags 复盘,成长 --cover-text "封面大字" < 正文文件
# 查看风格卡（人设/文风/话题习惯/封面规范）
& $C style show
```

### P2/P3 命令速查（数据回流 / 封面 / 真机自动化）

```powershell
# 登记一篇已发布笔记 / 看登记列表（发布器成功后会回填）
& $C posts add --note-id <24位笔记ID> --title "…" --tags 复盘,成长
& $C posts list
# 数据回流：创作者中心导出 CSV → 入库 → 趋势/归因报表
& $C stats import --file <导出的.csv>
& $C stats report            # 加 --out report.md 可落盘
# 统一风格封面（P3，本地渲染）
& $C covers make --day <YYYY-MM-DD>
# 真机自动化（⚠️ 只能在能访问小红书的机器上跑，见 OPERATION.md）
& $C live login              # 打开创作者中心扫码，登录态持久化
& $C live status             # 查登录状态
& $C live publish --day <YYYY-MM-DD> [--debug-shots]   # 发布前会确认
```

## 每日"今日帖子"流程（Agent 按此执行）

1. **看输入**：`journal today`（当日日志）+ `journal topics --days 30 --group tag`；没有当日日志就先请用户随手记几条。
2. **开草稿**：`studio new --day <今天>`，读 `drafts/<今天>/brief.md`。
3. **联网热点**：用 web 检索同领域"今天大家在聊什么 / 爆款标题结构"（轻量即可，3-5 条），回填 brief 的「同领域热点」小节（编辑该文件）。
4. **定选题**：从 当日输入 + 高频主题 + 热点 中给出 2-3 个候选，标注推荐理由，请用户拍板。
5. **成稿**（读 `config/style.json` 严格执行文风卡）：拟标题（短、钩子前置，给 3 个候选供选；标题保守控制在 20 字内）、写正文（3-6 段、口语化、结尾互动提问）、定话题（3-5 个，源自 tags+热点）、给 `cover_text` 封面大字建议。
6. **落盘**：用 `studio save` 写入 `drafts/<今天>/post.md`。
7. **复核**：把成品展示给用户确认（P1 结尾固定动作）；用户发布后如有数据（P2 起）回流优化。

## 常见任务

- 「帮我记录…」→ `journal add`（拿不准分类就 --category auto 并顺口问一句确认）。
- 「根据我的历史写今天帖子」→ 上述流程 1-7。
- 「看看我最近在写什么主题」→ `journal topics` 两档都跑，简单点评。
- 「改风格」→ 直接编辑 `C:\Harness_Projects\xhs-robot\config\style.json`（改完 style show 复核）。
- 「安装/更新本技能」→ 运行仓库根 `install.ps1`。

## 失败处理

- 中文乱码 → 先 `$env:PYTHONIOENCODING='utf-8'`。
- `studio new` 报"今日暂无日志" → 先引导用户记 2-3 条，再继续选题。
- 库被占用（SQLite locked）→ 等 1-2 秒重试；不要并发开多个写入进程。
- 命令不存在/参数报错 → 以 `cli.py --help` 与子命令 `-h` 为准，别凭记忆拼参数。

## 能力边界（诚实声明）

- **P1（可用）**：日志记录/分类/检索/主题聚合、风格卡、选题弹药、文案与话题生成、定稿落盘。
- **P2（发布链路已真机打通，2026-09-07 首次成功）**：Playwright 自动化可完成
  登录态检查→切"上传图文"→传图→填标题/正文（逐项校验）→数据回流入库。
  ⚠️ 两个已知限制：
  1) 最终「发布」按钮是 closed-shadow 自定义组件（`<xhs-publish-btn>`），自动化点不到，
     需有头窗口+真人点一次（脚本会填好内容并等待）；话题自动添加也不可靠（正文写 `#话题` 代替）；
  2) **发布请严格按 `C:\Harness_Projects\xhs-robot\PUBLISH_PLAYBOOK.md` 执行**，禁止即兴操作；
     成功判定以 posted 列表为准，页面里的 24 位 id 可能是误报。
  真机动作（登录/发布/取数）仍需在能访问小红书的网络下运行；风险与灰度纪律见 OPERATION.md。
- **P3（前半可用）**：统一风格封面 `covers make`。生图/漫画 API 待用户提供 key 后接入。
- 自动发布的"热度优化"只是提高概率；数据结论以创作者中心导出为准。
