"""把评测结果渲染成 markdown 报告。

报告里必须显式写清"判分器是谁、样本量多少"，因为 accuracy 的含义
完全取决于判分器是否可信——所以报告里必须把这两项摆在最显眼的位置。
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.schema import EvalReport
from eval.text import truncate

TYPE_LABELS = {
    "single_hop": "单跳",
    "multi_hop": "多跳",
    "unanswerable": "不可回答",
}

METRIC_LABELS: list[tuple[str, str]] = [
    ("count", "样本数"),
    ("accuracy", "综合正确率"),
    ("answer_accuracy", "可回答题正确率"),
    ("refusal_accuracy", "拒答正确率"),
    ("hallucination_rate", "幻觉率 ↓"),
    ("span_recall_at_k", "片段召回率@k"),
    ("hit_rate_at_k", "命中率@k"),
    ("mrr", "MRR"),
    ("ndcg_at_k", "nDCG@k"),
    ("latency_p50_ms", "延迟 P50 (ms)"),
    ("latency_p95_ms", "延迟 P95 (ms)"),
    ("tokens_per_item", "单条 token"),
    ("cost_total_usd", "总成本 (USD)"),
    ("errors", "调用错误数"),
]


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def render_markdown(report: EvalReport) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# 评测报告 `{report.run_id}`")
    add("")
    add(f"- 数据集：`{report.dataset}`")
    add(f"- 被测系统：`{report.system}`")
    add(f"- 判分器：`{report.judge}`")
    add(f"- 截断位置 k：{report.k}")
    add(f"- 运行时间：{report.started_at}")
    add("")

    if report.judge == "rule":
        add(
            "> ⚠ 本次使用**规则判分器**（字符 n-gram 相似度），"
            "它只用于验证评测框架本身能跑通，数值不能作为对外指标。"
            "真实指标必须用 LLM judge，并附人工校准一致率。"
        )
        add("")

    add("## 总览")
    add("")
    add("| 指标 | 数值 |")
    add("| --- | --- |")
    for key, label in METRIC_LABELS:
        if key in report.summary:
            add(f"| {label} | {_fmt(report.summary[key])} |")
    add("")

    if report.by_type:
        add("## 分类型")
        add("")
        columns = ["single_hop", "multi_hop", "unanswerable"]
        present = [c for c in columns if c in report.by_type]
        add("| 指标 | " + " | ".join(TYPE_LABELS.get(c, c) for c in present) + " |")
        add("| --- | " + " | ".join("---" for _ in present) + " |")
        for key, label in METRIC_LABELS:
            if key == "count":
                continue
            if any(key in report.by_type[c] for c in present):
                row = " | ".join(_fmt(report.by_type[c].get(key)) for c in present)
                add(f"| {label} | {row} |")
        add("")

    if report.calibration:
        add("## 判分器人工校准")
        add("")
        if report.calibration.get("labeled", 0) == 0:
            add(report.calibration.get("note", "尚无人工标注。"))
        else:
            add(f"- 已标注样本：{report.calibration['labeled']}")
            add(f"- judge 与人工一致率：{_fmt(report.calibration.get('agreement'))}")
            add(f"- Cohen's kappa：{_fmt(report.calibration.get('cohen_kappa'))}")
            disagreements = report.calibration.get("disagreements") or []
            if disagreements:
                add("")
                add("分歧样本（应逐条复核，判断是 judge 错还是人工错）：")
                add("")
                add("| id | judge | 人工 |")
                add("| --- | --- | --- |")
                for row in disagreements:
                    add(f"| `{row['id']}` | {row['judge']} | {row['human']} |")
        add("")

    failures = [r for r in report.results if r.verdict.judged and r.verdict.correct is False]
    if failures:
        add(f"## 错误样本（共 {len(failures)} 条，展示前 20 条）")
        add("")
        for result in failures[:20]:
            add(f"### `{result.item.id}` · {TYPE_LABELS.get(result.item.type, result.item.type)}")
            add("")
            add(f"- 问题：{result.item.question}")
            add(f"- 标准答案：{_fmt(result.item.gold_answer)}")
            add(f"- 系统回答：{truncate(result.answer.text, 200)}")
            add(
                f"- 判定：{result.verdict.reason}"
                f"（judge={result.verdict.judge}，score={_fmt(result.verdict.score)}）"
            )
            if result.retrieval.span_recall is not None:
                add(
                    f"- 检索：span_recall@{report.k}={_fmt(result.retrieval.span_recall)}，"
                    f"首个命中位次={_fmt(result.retrieval.first_hit_rank)}"
                )
            add("")

    unjudged = [r for r in report.results if not r.verdict.judged]
    if unjudged:
        add("## 未能判分的样本")
        add("")
        add(f"共 {len(unjudged)} 条。这些样本**不计入** accuracy，但必须出现在报告里，")
        add("否则判分失败会被伪装成「指标很好」。")
        add("")
        for result in unjudged[:10]:
            add(f"- `{result.item.id}`：{result.verdict.reason}")
        add("")

    return "\n".join(lines)


def write_report(report: EvalReport, out_dir: Path, tag: str | None = None) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.started_at.replace(":", "").replace("-", "").replace("+0000", "Z")
    safe_system = report.system.replace("/", "_").replace("(", "_").replace(")", "")
    stem = f"{tag + '__' if tag else ''}{safe_system}__{report.judge}__{stamp}"

    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
