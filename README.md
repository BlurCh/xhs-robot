# xhs-robot 小红书创作机器人（个人版）

记录日常 → 从个人历史选题 → 按统一风格成稿 → （P2）监控数据回流 → 优化。以 **DeepSeek Harness Skill** 形态交付，大脑为会话内 Agent，无需外部 LLM key。

## 目录结构

```
xhs-robot/
  cli.py            命令行入口（journal / studio / style / posts / stats / covers / live）
  db.py             SQLite 存储层（v1 journal；v2 posts/metrics 数据回流）
  style.py          风格卡加载 + 自动分类关键词规则
  studio.py         选题 brief 与帖子包 drafts/<day>/post.md
  covers.py         P3 统一风格封面模板引擎（Pillow 本地渲染）
  report.py         P2 数据回流：创作者中心 CSV 导入 + 趋势/归因报表
  site_auto.py      P2 真机自动化（Playwright：live login/status/publish）
  images.py         P3 生图流水线接口预留（待图像 API key）
  config/style.json 人设与文风风格卡（唯一事实来源）
  config/vision.json 生图服务配置（自动生成，enabled=false）
  data/xhs.db       本地历史库（个人内容，不提交 git）
  drafts/<day>/     brief.md 选题弹药 + post.md 定稿 + cover.png 封面
  skill/SKILL.md    DSH 技能本体；install.ps1 装入 .agents\skills\xhs-robot
  selftest.py       无框架自测：.venv\Scripts\python.exe selftest.py
  OPERATION.md      真机操作手册（登录/发布/取数，请照它走）
  setup.bat / live_login.bat / live_publish.bat / live_status.bat
```

## 快速上手（Windows PowerShell）

```powershell
$env:PYTHONIOENCODING='utf-8'
python C:\Harness_Projects\xhs-robot\cli.py journal add --auto --tags 读书,复盘 "今天读完《认知觉醒》…"
python C:\Harness_Projects\xhs-robot\cli.py journal today
python C:\Harness_Projects\xhs-robot\cli.py journal topics --days 30 --group tag
python C:\Harness_Projects\xhs-robot\cli.py studio new --day <YYYY-MM-DD>
python C:\Harness_Projects\xhs-robot\cli.py studio save --day <YYYY-MM-DD> --title "…" --tags 复盘,成长 --cover-text "…" < 正文.txt
```

## 三期路线（1→2→3 顺序）

| 期 | 内容 | 状态 |
|---|---|---|
| P1 | 日志中心 + 风格卡 + 选题/文案/定稿落盘（零外部依赖） | ✅ 完成 |
| P2 | 数据回流（db v2 + CSV 导入 + 趋势/归因报表）+ Playwright 真机自动化（`live login/publish`） | 代码完成 ✅；真机联调待你在本机运行 |
| P3 | 统一风格封面模板（已完成）+ 生图/漫画流水线（需图像 API key） | 封面 ✅；生图待 key |

> ⚠️ 重要：本 DSH 会话沙箱访问不到小红书（境内站点被出口限制），
> 「登录/发布/取数」请在你的本机按 **OPERATION.md** 操作（双击 `setup.bat` →
> `live_login.bat` → `live_publish.bat`）。沙箱内可跑：日志/选题/文案/封面/报表与全部自测。

## 风险与纪律（务必读）

1. **P2 属于网页自动化**：违反平台规则，有被限流/封号风险。只在**个人号（试验号）**上灰度；发布前默认向用户展示成稿确认。平台改版会导致选择器失效，需要维护。
2. 本工具不保证流量：小红书推荐是黑盒算法，文案/话题优化只提高概率。
3. Cookie、二维码、账号凭据不进对话、不进 git、不进日志。
4. **push 红线**：`data/`、`drafts/`、`.pw-profile/`（含登录态）、`.chrome-xhs*/`、`.venv/` 均在 .gitignore；推送到远端前先跑 `git ls-files | findstr /i "chrome pw-profile venv xhs.db"` 确认输出为空（本仓库历史已做过一次净化）。
5. 日志与草稿为个人内容，本地存储。
6. P1 生成的是**文案与帖子包**，不含图片；封面文字建议在 `post.md` 的 `cover_text` 字段，封面图由 `covers make` 生成。

## 自测

```powershell
python C:\Harness_Projects\xhs-robot\selftest.py
```

## 技能安装

```powershell
powershell -ExecutionPolicy Bypass -File C:\Harness_Projects\xhs-robot\install.ps1        # 当前会话项目根
powershell -ExecutionPolicy Bypass -File C:\Harness_Projects\xhs-robot\install.ps1 -DshHome  # 全部会话
```
