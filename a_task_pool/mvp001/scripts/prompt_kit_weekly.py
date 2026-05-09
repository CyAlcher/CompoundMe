#!/usr/bin/env python3
"""prompt_kit_weekly.py — 从 mirrorcop 会话库抽高频 prompt 簇，
生成周报 + task_pool 六字段 YAML 模板。stdlib + pyyaml。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_DB = Path.home() / ".ai-trace" / "data" / "ai_review.db"
DEFAULT_OUT = HERE / "out" / "weekly_report.md"
DEFAULT_TPL = HERE.parent / "templates"

PUNCT = re.compile(r"[^\w\s一-鿿]+", re.UNICODE)
WS = re.compile(r"\s+")
STOPWORDS = {"the", "a", "an", "is", "are", "i", "you", "it", "of", "to",
             "in", "on", "and", "or", "for", "with", "如何", "怎么", "什么",
             "这个", "那个", "请", "我", "的", "了", "是", "有", "和"}
NGRAM, THRESHOLD, MIN_CLUSTER, TOP_K, MIN_SAMPLES = 3, 0.5, 3, 5, 20
INTENT_KW = [
    ("debug", ["报错", "error", "debug", "异常", "失败", "traceback", "bug", "为空"]),
    ("summarize", ["总结", "概括", "解读", "分析", "阅读代码", "summary"]),
    ("transform", ["改写", "重写", "refactor", "转换", "修改", "优化"]),
    ("add-feature", ["实现", "新增", "加一个", "feature", "add", "支持"]),
    ("fetch", ["查", "获取", "抓取", "fetch", "搜索", "读取"]),
    ("publish", ["发布", "publish", "push", "提交", "部署"]),
]


def log(msg: str) -> None:
    print(f"[prompt-kit] {msg}", file=sys.stderr)


def fetch_prompts(db: Path, days: int) -> list[tuple[str, str]]:
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    sql = ("SELECT prompt_hash, text FROM prompt_records "
           "WHERE last_seen_date >= ? AND text NOT LIKE '# AGENTS.md%' "
           "AND text NOT LIKE '[Request interrupted%' "
           "AND text NOT LIKE 'Caveat:%' "
           "AND length(text) BETWEEN 8 AND 2000 ORDER BY last_seen_date DESC")
    with sqlite3.connect(str(db)) as con:
        return [(r[0], r[1]) for r in con.execute(sql, (cutoff,))]


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"'[^']{0,200}'|`[^`]{0,200}`|https?://\S+", " ", t)
    t = PUNCT.sub(" ", t)
    toks = [w for w in t.split()
            if (w not in STOPWORDS and len(w) > 1)
            or (len(w) == 1 and "一" <= w <= "鿿")]
    return " ".join(toks)


def ngrams(text: str) -> set[str]:
    s = WS.sub("", text)
    if len(s) < NGRAM:
        return {s} if s else set()
    return {s[i:i + NGRAM] for i in range(len(s) - NGRAM + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def cluster(recs: list[tuple[str, str]]) -> list[list[int]]:
    grams = [ngrams(normalize(r[1])) for r in recs]
    clusters: list[list[int]] = []
    centroids: list[set[str]] = []
    for i, g in enumerate(grams):
        if not g:
            continue
        best, sim = -1, 0.0
        for k, c in enumerate(centroids):
            s = jaccard(g, c)
            if s > sim:
                best, sim = k, s
        if best >= 0 and sim >= THRESHOLD:
            clusters[best].append(i)
        else:
            clusters.append([i])
            centroids.append(g)
    return clusters


def infer_intent(text: str) -> str:
    low = text.lower()
    for intent, kws in INTENT_KW:
        if any(kw in low for kw in kws):
            return intent
    return "summarize"


def truncate(text: str, limit: int = 200) -> str:
    t = text.strip().replace("\n", " ")
    return t if len(t) <= limit else t[:limit - 1] + "…"


def build_yaml(date: str, slug: str, typical: str, count: int) -> dict:
    return {
        "task_id": f"pk-{date}-{slug}",
        "domain": "research",
        "intent": infer_intent(typical),
        "input_refs": [],
        "contract": {
            "success_criteria": [f"复用该高频 prompt（样本 {count} 条）生成可用结果"],
            "failure_modes": [],
        },
        "human_in_loop": {"mode": "notify-after"},
        "notify": {"on_success": ["console:stdout"]},
        "exec": {"query": truncate(typical, 800), "output_format": "markdown"},
    }


def render_report(total: int, meta: list[dict], days: int, date: str) -> str:
    top_n = sum(c["count"] for c in meta)
    dup_rate = top_n / total if total else 0.0
    lines = [
        f"# prompt-kit 周报 · {date}", "",
        f"- 窗口：最近 {days} 天", f"- 会话数：{total}",
        f"- Top {TOP_K} 簇重复率：{dup_rate:.1%}",
        f"- 预计周省时：≈ {top_n * 3} 分钟（每次 3 分钟估）",
        "", "## Top 高频簇", "",
    ]
    for c in meta:
        lines += [
            f"### {c['rank']}. {c['slug']} — {c['count']} 次", "",
            f"- 模板：`templates/{c['filename']}`",
            f"- intent：`{c['intent']}`",
            "- 典型 prompt：", "",
            f"  > {truncate(c['typical'])}", "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--templates-dir", default=str(DEFAULT_TPL))
    args = ap.parse_args()

    db = Path(args.db).expanduser()
    if not db.exists():
        log(f"DB 不存在: {db}")
        return 2
    recs = fetch_prompts(db, args.days)
    log(f"读取 {len(recs)} 条 prompt（近 {args.days} 天）")
    if len(recs) < MIN_SAMPLES:
        log(f"样本 < {MIN_SAMPLES}，数据不足以聚类，退出")
        return 3

    clusters_idx = sorted(cluster(recs), key=len, reverse=True)
    hot = [c for c in clusters_idx if len(c) >= MIN_CLUSTER][:TOP_K]
    if not hot:
        log(f"没有 size ≥ {MIN_CLUSTER} 的簇，退出")
        return 4

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tpl_dir = Path(args.templates_dir)
    tpl_dir.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().strftime("%Y%m%d")
    meta = []
    for rank, indices in enumerate(hot, start=1):
        typical = max((recs[i][1] for i in indices), key=len)
        slug = f"c{rank:02d}-{hashlib.sha1(typical.encode()).hexdigest()[:6]}"
        data = build_yaml(date, slug, typical, len(indices))
        filename = f"{data['task_id']}.yaml"
        (tpl_dir / filename).write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        meta.append({"rank": rank, "slug": slug, "count": len(indices),
                     "typical": typical, "intent": data["intent"],
                     "filename": filename})

    out.write_text(render_report(len(recs), meta, args.days,
                                 dt.date.today().isoformat()), encoding="utf-8")
    log(f"周报 → {out}")
    log(f"模板 → {tpl_dir} ({len(meta)} 份)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
