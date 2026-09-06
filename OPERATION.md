# 真机操作手册（P2 自动发布 / 数据回流）

本仓库绝大部分功能（日志、选题、文案、封面、报表）在任何机器都能跑；
**只有「登录小红书 + 自动发布」需要在一台能访问小红书、且带桌面环境的机器上运行**
（例如你自己的电脑，双击 .bat 即可——不要在我这个沙箱会话里跑，这里到不了小红书）。

## 一、首次准备（一次即可）

1. 双击 `setup.bat`：建 `.venv`、装依赖、下载 Playwright Chromium（约 150MB，需联网）。
2. 双击 `live_login.bat`：弹出浏览器 → 用你的**个人号（试验号）**扫码登录。
   登录态保存在仓库 `.pw-profile/`，下次免扫码。

## 二、日常发布流程

```powershell
# 1) 记录今天的心情/经历/学习/想法（分类自动猜，可 --category 指定）
python cli.py journal add --auto --tags 复盘,读书 "今天读完《认知觉醒》…"

# 2) 打开选题弹药：看今天日志 + 近 30 天高频主题
python cli.py journal today
python cli.py journal topics --days 30 --group tag

# 3) 初始化草稿并让 Agent（在 DSH 会话里）生成标题/正文/话题/封面文案
python cli.py studio new --day <今天>
#    → 会话里告诉我"写今天的帖子"，我读 brief.md、联网补热点、按风格卡成稿
python cli.py studio save --day <今天> --title "…" --tags 复盘,成长 --cover-text "封面大字" < 正文.txt

# 4) 生成统一风格封面（无图也有一张能发的封面）
python cli.py covers make --day <今天>
#    想用多图：把图片放 drafts\<今天>\img\ 下（png/jpg/webp），封面则另用 cover.png

# 5) 人工复核 drafts\<今天>\post.md 与图片

# 6) 真机发布（会再让你确认一次；--yes 跳过确认）
#    方式 A：双击 live_publish.bat <今天>
#    方式 B：命令行 .\.venv\Scripts\python.exe cli.py live publish --day <今天>
#    ⚠️ 首次运行很可能要校准选择器（见第四节），请带 --debug-shots 跑并把截图发回
```

## 三、数据回流（监控自己的帖子表现）

- 创作者中心数据页 → 导出 CSV → 导入生成报表：
```powershell
python cli.py stats import --file <导出的.csv>
python cli.py stats report            # 或 --out report.md 落盘
```
- 发布器成功后会自动把笔记登记进 `posts`（`python cli.py posts list` 查看），
  之后定期导 CSV 即可看到每篇的曝光/观看/赞藏走势与"什么标题效果好"的归因线索。

## 四、页面改版 / 首次校准

自动化依赖网页结构，小红书随时可能改版。做法：
1. 用 `--debug-shots` 运行发布，产物在 `drafts\<今天>\debug\*.png`；
2. 把截图和发布日志发回 DSH 会话，我更新 `site_auto.py` 顶部的 `SELECTORS`；
3. 平常发布建议始终打开窗口（默认）人工盯着，别用 `--headless --yes` 无人值守。

## 五、风险与灰度纪律（务必遵守）

- 自动发布违反平台规则，有**限流/封号**风险。只在**个人号试验**上跑；
  连续 N 次成功、内容合规稳定后，才考虑正式号（届时仍建议窗口+人工盯）。
- 发布前必须人工过目最终标题/正文/图片（代码默认会确认一次）。
- Cookie/登录态在本地 `.pw-profile/`，勿复制外传、勿提交 git（已忽略）。
- 工具只提高"被更多人看到"的概率，不保证流量。

## 六、常见问题

- **中文乱码**：先执行 `$env:PYTHONIOENCODING='utf-8'` 再跑 python；双击 .bat 不受影响。
- **"图片为 0 张"**：把图放进 `drafts\<今天>\img\`，或先生成封面 `covers make`。
- **数据库被锁**：不要同时开两个写进程；等 1-2 秒重试。
- **发布后找不到 note_id**：到创作者中心人工核对，再用 `posts add --note-id …` 登记。
- **登录超时**：重跑 `live_login.bat`，扫码要快；3 分钟内完成。
