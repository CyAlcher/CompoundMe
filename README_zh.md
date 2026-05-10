<div align="center">

# CompoundMe

**你的 AI 协作，持续复利。**

> 看见它（L1）→ 标准化它（L2）→ 自动化它（L3）→ 让你的数字分身来处理（L4）

一套本地优先的工具包，把你每天已有的 AI 编程会话，
自动沉淀成可复用的任务模板，并通过三通道任务池持续执行。

[English](./README.md) ·
[快速开始](#快速开始) ·
[L1→L4 阶梯](#l1--l4-成长阶梯) ·
[项目结构](#项目结构) ·
[路线图](#路线图)

</div>

---

## 它解决什么问题

你每天用 AI 做了很多事，但：

- 不知道时间真正花在哪
- 同样的 prompt 反复手写，没有沉淀
- 重复性任务还是靠人肉执行，AI 只是"问答机"

**CompoundMe 把这件事反过来**：先把你的真实 AI 使用行为记录下来（L1），再从中挖出高频模式变成模板（L2），最后让任务池自动执行（L3）。用得越多，越省力——这是复利，不是线性提升。

---

## L1 → L4 成长阶梯

| 层级 | 含义 | 代码位置 |
|---|---|---|
| **L1 数字化** | 看清你每天真正用 AI 做了什么 | `src/ai_review_pipeline.py` → `~/.ai-trace/data/ai_review.db` |
| **L2 标准化** | 将高频 prompt 聚类成六字段任务模板 | `a_task_pool/mvp001/scripts/prompt_kit_weekly.py` |
| **L3 自动化** | 通过自动 / 通知 / 审批三通道路由标准化任务 | `a_task_pool/mvp001/cli.py` + `task_pool/router.py` |
| **L4 数字分身** | 由你的数字分身代为执行重复性工作 | 路线图中 —— L3 的六字段契约即为接入点 |

核心循环：

```
使用 AI → 采集行为 → 分类归因 → 资产化模式 → 复用 → 更好地使用 AI → 更多信号
```

---

## 快速开始

**环境要求：** Python 3.10+，macOS（launchd 调度）或任意系统（手动运行）。

```bash
# 1. 克隆并配置
git clone https://github.com/CyAlcher/compoundme.git
cd compoundme
cp config/app_config.example.json config/app_config.json
# 编辑 config/app_config.json，设置你的 AI 工具会话路径

# 2. 运行 L1 流水线，生成今日报告
cd src
python3 ai_review_pipeline.py --config ../config/app_config.json

# 3.（可选）macOS launchd 定时调度
python3 install_launchd.py --config ../config/app_config.json --load
```

报告写入配置中 `daily_root` 指定的目录。

---

## 与同类工具的差异

| 现有工具 | CompoundMe |
|----------------|-----------|
| LLM 可观测性（Langfuse、Phoenix） | 个人协作归因，而非请求追踪 |
| Prompt 管理工具 | Prompt 从真实会话中挖掘，而非手工整理 |
| 一次性分析 | 递归复利——用得越多，越精准 |
| 云端 / 团队优先 | 本地优先，数据完全自有 |

---

## 真实数据样例（已脱敏）

基于作者本人约 45 天、2200+ 条 prompt 的真实数据库运行（Claude Code / Codex / Cursor）。
所有 prompt 文本通过 `--anonymize` 脱敏——你看到的是结构，不是内容：

![CompoundMe 聚类演示](a_task_pool/mvp001/docs/cluster_demo.png)

- **左上**：按规模排列的 Top 20 聚类（红色 = 成为 YAML 模板的 Top 5）
- **右上**：窗口期内每日 prompt 量
- **左下**：聚类规模分布（长尾明显；少数高频聚类才是复利的来源）
- **右下**：Top 5 模板槽位，含意图 + 聚类规模

在自己的数据库上复现：

```bash
cd a_task_pool/mvp001
python scripts/viz_clusters.py --days 7 --anonymize --out docs/cluster_demo.png
```

---

## 项目结构

```
compoundme/
├── src/                        # MirrorCop —— L1 数字化
│   ├── ai_review_pipeline.py   # 主流水线：解析 → 存储 → 报告
│   ├── monitor_review.py       # 告警监控：检查流水线是否运行
│   ├── install_launchd.py      # macOS launchd plist 生成器
│   ├── config_loader.py        # 配置加载（支持深度合并默认值）
│   └── run_review.sh / monitor_review.sh
├── config/
│   ├── app_config.example.json
│   └── mail_config.example.json
├── a_task_pool/mvp001/         # prompt-kit —— L2 标准化 / L3 自动化
│   ├── scripts/prompt_kit_weekly.py    # 挖掘数据库 → 周报 + YAML 模板
│   ├── scripts/viz_clusters.py         # 聚类可视化
│   ├── cli.py                          # submit / run / list / approve / show
│   ├── task_pool/                      # 六字段 schema、任务池、路由器
│   ├── executors/                      # echo / shell / stub
│   └── templates/example_*.yaml        # 脱敏参考模板
└── README.md
```

---

## 支持的 AI 工具

| 工具 | 会话路径（默认） | 格式 |
|------|----------------------|--------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | JSONL |
| OpenAI Codex CLI | `~/.codex/sessions/**/*.jsonl` | JSONL |
| Cursor | `~/.cursor/projects/**/agent-transcripts/*.jsonl` 和 `**/state.vscdb` | JSONL + SQLite |

---

## L2 → L3：prompt-kit

```bash
# 1. 安装依赖
pip install -r a_task_pool/mvp001/requirements.txt

# 2. 挖掘高频 prompt → 生成 pk-*.yaml 模板（本地私有，已 gitignore）
cd a_task_pool/mvp001
python scripts/prompt_kit_weekly.py --days 7

# 3. 提交模板到任务池并执行
python cli.py submit templates/example_fetch.yaml
python cli.py run --max-tasks 1

# 4. 查看任务状态
python cli.py list
```

---

## 隐私说明

- 所有数据**本地存储**，不向任何外部服务发送
- prompt 文本中的绝对 home 路径自动脱敏为 `~`
- `.gitignore` 已排除 `data/`、`logs/`、`state/` 和所有 `*.db` 文件
- `mail_config.json`（SMTP 凭据）同样已排除

---

## 路线图

- [ ] T 日快照层（每日增量，而非仅累计）
- [ ] 资产注册表：将技能、prompt 和数字分身作为一等公民管理
- [ ] 注册资产的前后效果对比
- [ ] token 和轮次统计
- [ ] **L4 数字分身**：在六字段契约后接入真实执行器（Claude Code / n8n），让重复性工作无需你参与

---

## 参与共建

- **提 Issue**：漏掉哪类场景、框架跑偏、想加新功能都欢迎
- **提 PR**：改错别字、补示例命令、优化 prompt 都欢迎
- 请勿在示例中提交任何个人会话数据、API 密钥或真实 prompt 内容

---

## 关注作者

左边是**公众号**，更新项目动态与 AI 协作复利的实战内容；
右边是**个人微信**，交流、反馈、提 bug、商业合作都欢迎。

<table>
  <tr>
    <td align="center">
      <img src="imgs/gongzhonghao.jpg" alt="微信公众号" width="200"><br>
      <sub>微信公众号</sub>
    </td>
    <td align="center">
      <img src="imgs/kefu.png" alt="个人微信" width="200"><br>
      <sub>个人微信（交流 / 反馈）</sub>
    </td>
  </tr>
</table>

---

## 许可证

**双重许可——非商业使用免费，商业使用需付费授权。** 完整条款见 [`LICENSE`](./LICENSE)。

- **非商业用途**（个人使用、学术研究、评估、非营利开源贡献）：免费，须遵守 LICENSE 中的署名和命名条款。
- **商业用途**（付费产品、SaaS、内部营利性使用、收费再发行）：需单独商业授权。请在 GitHub Issue 中以 `[commercial]` 前缀开启沟通。

Copyright (c) 2026 CyAlcher. All rights reserved.
