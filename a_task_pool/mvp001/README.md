# AI-Ready 任务池 MVP

对齐方案 `自动化工作流方案.md` §1-§6 的最小可跑版本。

## 架构（五层中的 L1/L2/L3/L4/L6）

```
L1 入口    task_pool/schema.py + loader.py    Pydantic v2 六字段契约
L2 任务池  task_pool/pool.py                  SQLite + WAL，幂等 + 四态
L3 路由    task_pool/router.py                intent → (channel, executor)
L4 执行    executors/base.py                  echo + shell + claude_code/n8n stub
L6 通知    task_pool/notify.py                console + 可选 SMTP
CLI        cli.py                             submit / run / list / approve / show
```

未实现：L5 Langfuse 观测、三通道独立 worker 进程池（MVP 单循环足够）、
Excel → JSON 转换、签名审批链接、日报聚合、真实 Claude Code/n8n/OpenClaw adapter。

## 安装

```bash
cd a_task_pool/mvp001
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 快速开始

```bash
# 1. 提交一个合法 YAML（domain=data-ops, intent=fetch → Auto 通道）
python cli.py submit examples/data_ops_fetch.yaml

# 2. 跑池子（直到空）
python cli.py run

# 3. 列出所有任务
python cli.py list

# 4. 看单个任务的完整 payload
python cli.py show do-2026-05-09-fetch
```

## 三通道示例

```bash
# Auto：自动执行，无须审批
python cli.py submit examples/data_ops_fetch.yaml
python cli.py run --channel auto

# Notify-After：自动执行，事后通知（MVP 版：on_success/on_failure 必触发）
python cli.py submit examples/social_media_publish.yaml
python cli.py run --channel notify

# Approve-Before：入池后处于 awaiting_approval，必须手动 approve 才会被 run 拉起
python cli.py submit examples/data_ops_delete_approve.yaml
python cli.py approve do-2026-05-09-delete
python cli.py run --channel approve
```

## Schema 拒绝演示

```bash
python cli.py submit examples/bad_missing_criteria.yaml
# Task 校验失败 (.../bad_missing_criteria.yaml):
#   - contract.success_criteria: Field required
```

## 测试

```bash
pip install pytest
pytest tests/ -v
```

## 邮件通知（可选）

默认通知降级到 stderr。要启用 SMTP，设置环境变量：

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_USER=you@example.com
export SMTP_PASSWORD=xxx
export SMTP_FROM="agent@example.com"
```

YAML 里写 `notify.on_success: ["email:x@y.com"]` 即可。

## 六字段契约（方案 §1.2）

```yaml
task_id: "mm-2026-05-09-001"    # 幂等键
domain: "data-ops"               # social-media / github-dev / data-ops / research
intent: "fetch"                  # 动词+宾语
input_refs: []                   # 领域输入的指针
contract:
  success_criteria: ["..."]      # 必填，至少一条
  failure_modes: []
  test_command: null
human_in_loop:
  mode: "none"                   # none / notify-after / approve-before
  reviewers: []                  # approve-before 时必填
notify:
  on_success: ["email:..."]      # email: / console: / lark: / telegram:
  on_failure: []
exec: {...}                      # 领域扩展字段，按 domain 校验
```

## 下一步接入点（保留 hook）

- `executors/base.py` 里的 `ClaudeCodeExecutor` / `N8nWebhookExecutor` 是 stub，
  换成真实实现即可无缝切换（路由层不用改）。
- `task_pool/notify.py` 里的 lark / telegram 前缀目前降级到 console，
  补一个 `_send_lark()` 就能接入。
- Excel 录入：写一个独立脚本 pandas 读 → list[dict] → `load_from_dict` 批量入池，
  不要侵入 loader。
