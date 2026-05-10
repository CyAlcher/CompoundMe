# CompoundMe

> 你的 AI 协作，持续复利。看见它（L1）→ 标准化它（L2）→ 自动化它（L3）→ 让你的数字分身来处理（L4）。

**CompoundMe** 是一个本地优先的工具包，帮你从每天已有的 AI 编程会话中构建个人数字分身体系。它包含两个核心模块：

- **MirrorCop**（`src/`）—— L1 镜像层。将 Claude Code / Codex CLI / Cursor 的会话日志解析写入本地 SQLite 数据库，并将这些事件转化为 ROI 和资产证据台账。
- **prompt-kit**（`a_task_pool/mvp001/`）—— L2→L3 消费层。从镜像数据库中挖掘高频 prompt，将其转化为可复用的六字段 YAML 模板，并送入本地任务池（自动 / 事后通知 / 事前审批 三通道）。

所有数据留在你的机器上。无云端，无厂商锁定，prompt 数据永远不会离开 `~/.ai-trace/`。

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

这不是线性提升，而是复利。

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

基于作者本人的真实 AI 会话数据库运行（约 45 天内 2200+ 条 prompt，来自 Claude Code / Codex / Cursor）。
所有典型 prompt 文本通过 `--anonymize` 脱敏后截图——你看到的是结构，不是内容：

![CompoundMe 聚类演示](a_task_pool/mvp001/docs/cluster_demo.png)

- 左上：按规模排列的 Top 20 聚类（红色 = 成为 YAML 模板的 Top 5）
- 右上：窗口期内每日 prompt 量
- 左下：聚类规模分布（长尾明显：大多数 prompt 是一次性的；少数高频聚类才是复利的来源）
- 右下：Top 5 模板槽位，含意图 + 聚类规模（prompt 文本已脱敏）

在自己的数据库上复现：

```bash
cd a_task_pool/mvp001
python scripts/viz_clusters.py --days 7 --anonymize --out docs/cluster_demo.png
```

---

## 功能特性

- 解析来自 **Claude Code**、**OpenAI Codex CLI** 和 **Cursor** 的本地会话文件
- 支持从 Cursor 的 transcript JSONL 和工作区 `state.vscdb` 两种格式导入
- 对 prompt 去重并按类别和偏好信号分类
- 存储事件元数据：`session_id`、`turn_id`、`event_time`、`project_path`、`cwd`、`artifact_path`、`artifact_type`
- 维护任务台账，含 `project_id`、结果标签、prompt 关联和产物关联
- 导出 ROI、资产效果和数据质量报告（Markdown / JSON）
- 所有数据存入本地 **SQLite** 数据库——无云端，无厂商锁定
- 生成**每日**和**每周** Markdown 报告
- 可选**邮件告警**（当日流水线未运行时触发）
- macOS **launchd** 调度支持（自动生成 plist）
- 完全**配置驱动**——所有路径、调度和规则均在 `app_config.json` 中定义

---

## 项目结构

```
compoundme/
├── src/                        # MirrorCop —— L1 数字化
│   ├── config_loader.py        # 配置加载（支持深度合并默认值）
│   ├── ai_review_pipeline.py   # 主流水线：解析 → 存储 → 报告
│   ├── monitor_review.py       # 告警监控：检查流水线是否运行
│   ├── install_launchd.py      # macOS launchd plist 生成器 + 安装器
│   ├── run_review.sh           # 流水线 Shell 封装
│   └── monitor_review.sh       # 监控 Shell 封装
├── config/
│   ├── app_config.example.json
│   └── mail_config.example.json
├── a_task_pool/mvp001/         # prompt-kit —— L2 标准化 / L3 自动化
│   ├── scripts/prompt_kit_weekly.py    # 挖掘数据库 → 周报 + YAML 模板
│   ├── scripts/viz_clusters.py         # 可选聚类可视化
│   ├── cli.py                          # submit / run / list / approve / show
│   ├── task_pool/                      # 六字段 schema、任务池、路由器
│   ├── executors/                      # echo / shell / stub
│   ├── examples/                       # schema 示例
│   └── templates/example_*.yaml        # 脱敏参考模板
└── README.md
```

---

## 快速开始

**环境要求：** Python 3.10+，macOS（使用 launchd 调度）或任意系统（手动运行）。

### 1. 克隆并配置

```bash
git clone https://github.com/CyAlcher/compoundme.git
cd compoundme

cp config/app_config.example.json config/app_config.json
# 编辑 config/app_config.json —— 设置你的源路径和输出目录
```

### 2. 手动运行

```bash
cd src
python3 ai_review_pipeline.py --config ../config/app_config.json
```

报告将写入配置中 `daily_root` 指定的目录。

### 3.（可选）macOS launchd 定时调度

```bash
cd src
python3 install_launchd.py --config ../config/app_config.json --load
```

将自动生成并加载两个 launchd 任务：
- `compoundme-runner` —— 每天在配置的时间运行流水线
- `compoundme-monitor` —— 检查是否有漏跑，并可选发送邮件告警

### 4.（可选）启用邮件告警

```bash
cp config/mail_config.example.json config/mail_config.json
# 填写 SMTP 凭据并设置 "enabled": true
```

---

## 配置说明

所有行为由 `config/app_config.json` 控制，主要配置项：

| 配置节 | 用途 |
|---------|---------|
| `paths` | 数据库、日志、状态和报告的存储路径 |
| `sources` | 本地 AI 工具会话目录路径 |
| `filters` | 噪声模式和需排除的路径子串 |
| `schedule` | launchd runner 和 monitor 的运行时间 |
| `mail` | 告警邮件的 mail_config.json 路径 |
| `reports` | 文件夹命名规则和报告文件名 |

完整注释模板见 `config/app_config.example.json`。

---

## 支持的 AI 工具

| 工具 | 会话路径（默认） | 格式 |
|------|----------------------|--------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | JSONL |
| OpenAI Codex CLI | `~/.codex/sessions/**/*.jsonl` | JSONL |
| Cursor | `~/.cursor/projects/**/agent-transcripts/*.jsonl` 和 `**/state.vscdb` | JSONL + SQLite |

如需接入新工具，在 `ai_review_pipeline.py` 中实现 `parse_<tool>(path)` 生成器，并在配置的 `sources` 中添加对应路径。

---

## Prompt 分类

| 类别 | 说明 |
|----------|-------------|
| `code_reading` | 阅读、追踪逻辑、理解上下游 |
| `code_modification` | 修改、重构、修复、替换代码 |
| `env_tooling` | 环境配置、安装报错、工具设置 |
| `prompt_experiment` | CoT、few-shot、消融实验、稳定性测试 |
| `structured_output` | Markdown、表格、报告、格式化输出 |
| `risk_assessment` | 规划、风险评估、影响分析 |
| `digital_asset` | 技能、模板、自动化、个性化 |
| `other` | 其他所有内容 |

---

## 数据库结构

```sql
prompt_records (
  prompt_hash, tool, source_file, source_mtime, text, assistant, category,
  first_seen_date, last_seen_date, session_id, turn_id, parent_turn_id,
  event_time, project_path, cwd, source_kind, model_name, tool_call_name,
  artifact_path, artifact_type, outcome_status, task_confidence,
  input_tokens, output_tokens, cache_read_tokens
)

pipeline_runs (run_id, run_date, run_at, run_type, status,
               raw_session_count, unique_prompt_count, notes)

monitor_alerts (alert_key, alert_date, status, message, created_at)

task_runs (
  task_id, task_date, owner, task_type, task_name, project_id,
  delivery_type, delivery_status, rework_count,
  outcome_status, reuse_result, business_value, notes, created_at
)
task_prompt_links (task_id, prompt_hash)
task_artifacts (artifact_id, task_id, artifact_path, artifact_type, notes, created_at)
```

## MVP1 任务台账与审计报告

### 创建任务

```bash
cd src
python3 task_ledger.py --config ../config/app_config.json create-task \
  --task-id task-20260325-report-01 \
  --task-date 2026-03-25 \
  --owner alice \
  --task-type report \
  --task-name "客户 ROI 复盘" \
  --delivery-type markdown_report \
  --rework-count 1
```

### 关联 prompt 到任务

```bash
cd src
python3 task_ledger.py --config ../config/app_config.json link-prompts \
  --task-id task-20260325-report-01 \
  --prompt-hash HASH_A HASH_B
```

### 导出 / 导入批量任务复盘

```bash
cd src
python3 task_ledger.py --config ../config/app_config.json export-task-review \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --output ../out/task_review.csv

python3 task_ledger.py --config ../config/app_config.json import-task-review \
  --input ../out/task_review.csv
```

### 从 prompt 证据自动关联产物

```bash
cd src
python3 task_ledger.py --config ../config/app_config.json autolink-artifacts \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --owner alice
```

### 生成数据质量报告

```bash
cd src
python3 data_quality_report.py --config ../config/app_config.json \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --owner alice \
  --output-dir ../out/data_quality
```

### 生成 ROI 审计报告

```bash
cd src
python3 roi_audit_report.py --config ../config/app_config.json \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --owner alice \
  --output ../out/roi_audit_report.md
```

### 导出汇总包

```bash
cd src
python3 export_audit_pack.py --config ../config/app_config.json \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --owner alice \
  --output-dir ../out/audit_pack
```

输出文件：

- `audit_summary.md`
- `audit_manager_brief.md`
- `roi_audit_report.md`
- `client_summary.md`
- `owner_summary.md`
- `data_quality_report.md`
- `data_quality_report.json`

### 运行测试

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
```

---

## 隐私说明

- 所有数据**本地存储**——不向任何外部服务发送
- prompt 文本中的绝对 home 路径自动脱敏为 `~`
- `.gitignore` 已排除 `data/`、`logs/`、`state/` 和所有 `*.db` 文件
- `mail_config.json`（SMTP 凭据）同样已排除

---

## 路线图

- [ ] T 日快照层（每日增量，而非仅累计）
- [ ] 资产注册表：将技能、prompt 和数字分身作为一等公民管理
- [ ] 注册资产的前后效果对比
- [ ] 每次会话的 token 和轮次统计
- [ ] 更高覆盖率的结果标签和产物绑定
- [ ] 更健壮的周期性交付工作项目级汇总
- [ ] **L4 数字分身**：在六字段契约后接入真实执行器（Claude Code / n8n），让重复性工作无需你参与

---

## 许可证

**双重许可——非商业使用免费，商业使用需付费授权。** 完整条款见 [`LICENSE`](./LICENSE)。

- **非商业用途**（个人使用、学术研究、评估、非营利开源贡献）：免费，须遵守 LICENSE 中的署名和命名条款。
- **商业用途**（付费产品、SaaS、内部营利性使用、基于本代码的付费咨询 / 培训、收费再发行）：需单独商业授权。请在 GitHub Issue 中以 `[commercial]` 前缀开启沟通。

Copyright (c) 2026 CyAlcher. All rights reserved.

---

## L2 → L3：prompt-kit（a_task_pool/mvp001）

L2 标准化和 L3 自动化步骤位于 `a_task_pool/mvp001/`。
`prompt_kit_weekly.py` 从 L1 镜像数据库中挖掘高频 prompt，将其转化为可复用的六字段 YAML 任务模板；`cli.py` 将这些模板送入本地任务池的自动 / 通知 / 审批三通道。

快速开始：

```bash
# 1. 安装依赖（如需与 L1 镜像运行时隔离，可使用独立环境）
pip install -r a_task_pool/mvp001/requirements.txt

# 2. 从自己的数据库挖掘 → 周报 + pk-*.yaml 模板（已 gitignore，仅本地保留）
cd a_task_pool/mvp001
python scripts/prompt_kit_weekly.py --days 7   # 默认读取 ~/.ai-trace/data/ai_review.db

# 3. 将脱敏示例（或自己挖掘的模板）提交到本地任务池
python cli.py submit templates/example_fetch.yaml

# 4.（可选）聚类可视化
python scripts/viz_clusters.py --days 7
```

`templates/pk-*.yaml` 是**你自己**挖掘出的产物（含真实 prompt 文本），已 gitignore，不会提交。`templates/example_*.yaml` 是脱敏参考样本，可安全提交和分享。设计说明见 `a_task_pool/自动化工作流方案.md`。

---

## 参与共建

欢迎提 Issue 和 PR。请勿在示例中提交任何个人会话数据、API 密钥或真实 prompt 内容。

---

## 关注作者

扫码关注微信公众号，获取版本动态、使用技巧以及 L1→L4 数字分身实践的深度内容。

<p align="center">
  <img src="docs/wechat_official_qr.jpg" alt="CompoundMe 微信公众号" width="220" />
</p>

商业授权咨询请参阅[许可证](#许可证)部分，或在 GitHub Issue 中以 `[commercial]` 前缀开启沟通。
