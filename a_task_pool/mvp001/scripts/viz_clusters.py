#!/usr/bin/env python3
"""viz_clusters.py — 从 mirrorcop DB 抽 N 天 prompt 跑聚类，画 4 宫格图：
1) Top 20 簇 size 柱状；2) 每日 prompt 量；3) 簇 size 长尾分布；
4) Top 5 簇 intent 占比。仅用 stdlib + pyyaml（已装）+ matplotlib。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prompt_kit_weekly import (  # noqa: E402
    fetch_prompts, cluster, infer_intent, truncate, TOP_K, MIN_CLUSTER,
)

DEFAULT_DB = Path.home() / ".ai-trace" / "data" / "ai_review.db"
DEFAULT_OUT = HERE / "out" / "cluster_viz.png"

for fam in ("PingFang SC", "Heiti SC", "STHeiti", "Songti SC", "Arial Unicode MS"):
    rcParams["font.sans-serif"] = [fam] + rcParams.get("font.sans-serif", [])
rcParams["axes.unicode_minus"] = False


def per_day(db: Path, days: int) -> list[tuple[str, int]]:
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    with sqlite3.connect(str(db)) as con:
        return [(r[0], r[1]) for r in con.execute(
            "SELECT first_seen_date, COUNT(*) FROM prompt_records "
            "WHERE first_seen_date >= ? GROUP BY first_seen_date "
            "ORDER BY first_seen_date", (cutoff,))]


def plot(db: Path, days: int, out: Path, anonymize: bool = False) -> None:
    recs = fetch_prompts(db, days)
    clusters_idx = sorted(cluster(recs), key=len, reverse=True)
    sizes = [len(c) for c in clusters_idx]
    top20 = sizes[:20]
    hot = [c for c in clusters_idx if len(c) >= MIN_CLUSTER][:TOP_K]
    typicals = [max((recs[i][1] for i in c), key=len) for c in hot]
    intents = [infer_intent(t) for t in typicals]
    daily = per_day(db, days)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f"prompt-kit 聚类可视化 · 近 {days} 天 · {len(recs)} 条 prompt",
        fontsize=14, fontweight="bold",
    )

    ax = axes[0][0]
    colors = ["#E74C3C" if i < TOP_K else "#3498DB" for i in range(len(top20))]
    ax.bar(range(len(top20)), top20, color=colors)
    ax.set_title(f"Top 20 簇 size（红=Top {TOP_K} 生成模板）")
    ax.set_xlabel("簇排名"); ax.set_ylabel("prompt 数")
    for i, v in enumerate(top20):
        ax.text(i, v + 0.2, str(v), ha="center", fontsize=8)

    ax = axes[0][1]
    if daily:
        xs = [d[0][5:] for d in daily]
        ys = [d[1] for d in daily]
        ax.plot(xs, ys, marker="o", color="#27AE60", linewidth=1.6)
        ax.fill_between(range(len(xs)), ys, alpha=0.2, color="#27AE60")
        ax.set_title(f"每日 prompt 量（合计 {sum(ys)}）")
        ax.set_xlabel("日期 MM-DD"); ax.set_ylabel("条数")
        step = max(1, len(xs) // 12)
        ax.set_xticks(range(0, len(xs), step))
        ax.set_xticklabels([xs[i] for i in range(0, len(xs), step)],
                           rotation=45, ha="right", fontsize=8)

    ax = axes[1][0]
    buckets = {"1 (单例)": 0, "2": 0, "3-5": 0, "6-10": 0, "11-20": 0, ">20": 0}
    for s in sizes:
        if s == 1: buckets["1 (单例)"] += 1
        elif s == 2: buckets["2"] += 1
        elif s <= 5: buckets["3-5"] += 1
        elif s <= 10: buckets["6-10"] += 1
        elif s <= 20: buckets["11-20"] += 1
        else: buckets[">20"] += 1
    ax.bar(buckets.keys(), buckets.values(), color="#8E44AD")
    ax.set_title(
        f"簇 size 分布（共 {len(sizes)} 簇，"
        f"{buckets['1 (单例)'] / max(1, len(sizes)):.0%} 是单例长尾）"
    )
    ax.set_xlabel("簇 size 区间"); ax.set_ylabel("簇数")
    for i, (_, v) in enumerate(buckets.items()):
        ax.text(i, v + max(buckets.values()) * 0.01, str(v),
                ha="center", fontsize=9)

    ax = axes[1][1]
    ax.axis("off")
    ax.set_title(f"Top {TOP_K} 模板一览")
    lines = []
    for i, (c, it, tp) in enumerate(zip(hot, intents, typicals), 1):
        lines.append(f"#{i}  {len(c):>2} 次  [{it}]")
        if anonymize:
            lines.append(f"    [redacted · intent={it} · size={len(c)}]")
        else:
            lines.append(f"    {truncate(tp, 60)}")
        lines.append("")
    ax.text(0.01, 0.98, "\n".join(lines), transform=ax.transAxes,
            va="top", ha="left", fontsize=9)

    plt.tight_layout(rect=(0, 0, 1, 0.96))
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=140, bbox_inches="tight")
    print(f"[viz] → {out}  ({out.stat().st_size // 1024} KB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--anonymize", action="store_true",
                    help="redact typical prompt text (safe to share)")
    args = ap.parse_args()
    plot(Path(args.db).expanduser(), args.days, Path(args.out),
         anonymize=args.anonymize)
    return 0


if __name__ == "__main__":
    sys.exit(main())
