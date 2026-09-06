# XHS 发布手册（PLAYBOOK）— 经验固化版

> 来源：2026-09-07 首次真机发布完整校准（含多次失败复盘）。
> 目的：以后发布**按本手册走，不许再瞎试**。发布 = 确定性流程，失败走对照表。

## 0. 前置检查（每次必做）

```powershell
cd C:\Harness_Projects\xhs-robot
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe cli.py live status        # 登录态=ok
.\.venv\Scripts\python.exe cli.py env net             # 国内可达=True
```
任一不满足 → 先解决（登录/关 VPN），**不得跳过直接发布**。

## 1. 发布流程（已校准，顺序不可乱）

1. `studio new/save` 准备定稿 `drafts/<day>/post.md`（标题/正文/tags/cover_text），
   `covers make` 生成封面（至少 1 张图，图片也可放 `drafts/<day>/img/`）。
2. 发布命令（发布前会打印内容并要求 y 确认）：
   ```
   'y' | cli.py live publish --day <YYYY-MM-DD> --debug-shots
   ```
3. 代码内部顺序（勿随意改）：
   - 打开 `creator.xiaohongshu.com/publish/publish` —— **这是类型选择页**；
   - **必须点「上传图文」标签**（`text=上传图文` 取 .last），否则会进视频上传分支；
   - 上传图：找 `input[type=file]` 中 `accept` 含 `jpg` 的那个 `set_input_files`；
   - 等**标题框出现**：`input[placeholder*="填写标题"]`（class `d-text`）→ fill 并**校验值**；
   - 正文：`.tiptap.ProseMirror`（contenteditable）→ fill 并**校验 inner_text ≥50 字**；
   - **标题/正文任一未通过校验 → 中止**（导出 dom-*.json + 截图），绝不点发布；
   - 话题：工具栏按钮文案是「**话题**」(contentBtn topic-btn)，不是"添加话题"；
     自动加话题当前不可靠 → 可在正文里写 `#话题`，或发布后手动补（已知限制）；
   - 提交按钮是自定义组件 **`<xhs-publish-btn>`（closed shadow DOM）**：
     文字/DOM 扫描都看不见，见第 2 节触发方式；
   - 点发布后：等待 → 用 posted 列表 API 复核（见第 3 节判定）。

## 2. 「发布」按钮触发（当前唯一需注意的点）

- 红色底白字"发布"，位于底栏/右下。
- 它是 Web Component，**shadowRoot 为 closed**，普通 JS/CSS/选择器不可达；
  headless 下坐标点击曾失败（可能按钮当时未就绪或视口差异）。
- **目前 100% 可靠方式**：`--headless` 改为有头窗口（viewport 1400×900），
  内容填好后由真人点一次红按钮（首次 2026-09-07 已验证成功），期间脚本录网络+轮询成功文案。
- 待办（可选自动化）：记录真实提交请求 → 直接调发布 API；或研究 closed shadow 坐标触发。
  **未完成前，不要把"点发布"放进无人值守流程。**

## 3. 成功判定（防误报，重要）

- 页面/URL 里出现任意 24 位十六进制串**不是**成功证据（曾误报 note_id）。
- 真判定 = 拉一次 posted 列表：`cli.py live pull` →
  读 `pulls/network-*.json` 中 `note/user/posted` 的 `notes[]`，
  **标题出现在列表里**才算发布成功 → 再 `stats pull-import` 入库、拿真实 note_id。
- 页面出现「发布成功/审核中」文案可作为旁证。

## 4. 失败对照表

| 症状 | 原因/处置 |
|---|---|
| 填完点发布没反应 | 大概率按钮未就绪或点击错位 → 有头窗口真人点一次（第 2 节） |
| 找不到标题/正文框 | 没切"上传图文"或图未传完 → 检查 dom-*.json 与步骤日志 |
| note_id 有但线上没有 | 误报 → 以 posted 列表复核（第 3 节） |
| 被带入视频上传页 | 漏点"上传图文"标签 |
| 话题数为 0 | 已知限制：正文写 #话题 或手动补 |
| 超时 120s | 记得命令用 `timeoutMs`（驼峰），发布全流程 ~2-4 分钟属正常 |
| 报"登录 required" | 先 `live login` 扫码 |

## 5. 数据侧备忘（校准过的字段）

- 已发布列表：`/api/galaxy/v2/creator/note/user/posted?tab=0&page=0`
  字段：`id`(note_id)、`display_title`、`view_count`、`likes`、`collected_count`、
  `comments_count`、`shared_count`、`visible_time`(epoch 秒，作发布日)、`images_list`。
- 账号级趋势：`/api/galaxy/v2/creator/datacenter/account/base` →
  `data.seven/thirty.*_list`，**`impl_count` = 界面"曝光数"**（已核对）。
- 单篇详情：`/api/galaxy/creator/data/note_detail_new`（GET；7/30 天窗口，
  老帖窗口期外为 0 属正常）。

## 6. 纪律（写死）

- 只发实验号灰度；发布前确认；删除/编辑/设为私密前单独确认。
- 不在同一秒连发；不发即删循环；内容必须出自真实素材并经用户定稿。
- Cookie/登录态在 `.pw-profile/`，不进 git、不进对话日志。
