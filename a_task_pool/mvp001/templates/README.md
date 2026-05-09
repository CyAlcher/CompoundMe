# templates/

`prompt_kit_weekly.py` 生成的 **`pk-<yyyymmdd>-<slug>.yaml`** 属于你自己的会话加工结果，**不入库**（已在 `.gitignore` 中按 `pk-*.yaml` 过滤）。

本目录只保留公共脱敏样板：`example_*.yaml`，展示六字段契约长什么样、domain/intent/human_in_loop/notify 如何组合。

生成自己的模板：

```bash
python scripts/prompt_kit_weekly.py --days 7
# 产出落在本目录：pk-<date>-*.yaml
```

把模板推进任务池：

```bash
python cli.py submit templates/pk-<date>-<slug>.yaml
```
