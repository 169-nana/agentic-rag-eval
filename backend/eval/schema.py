"""评测与数据模型。

一个关键设计决定：**评测集的"标准答案"以原文片段（gold span）为准，而不是 chunk id。**

原因：本周要做的"分块策略消融"会改变 chunk 的切分方式，如果 gold 绑死 chunk id，
每换一种分块就得重新标注一遍评测集，实验无法进行。
改成"gold 是文档里逐字出现的原文片段"，检索是否命中就通过**文本覆盖度**判定，
这样同一份评测集可以评测任意分块策略。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ItemType = Literal["single_hop", "multi_hop", "unanswerable"]


# --------------------------------------------------------------------------- #
# 评测集
# --------------------------------------------------------------------------- #
@dataclass
class GoldSpan:
    """文档中逐字出现的原文片段，是判断检索是否命中的依据。"""

    doc_id: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldSpan:
        return cls(doc_id=data["doc_id"], text=data["text"])


@dataclass
class EvalItem:
    id: str
    question: str
    type: ItemType
    answerable: bool
    gold_answer: str | None = None
    gold_spans: list[GoldSpan] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "type": self.type,
            "answerable": self.answerable,
            "gold_answer": self.gold_answer,
            "gold_spans": [s.to_dict() for s in self.gold_spans],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalItem:
        return cls(
            id=data["id"],
            question=data["question"],
            type=data["type"],
            answerable=bool(data["answerable"]),
            gold_answer=data.get("gold_answer"),
            gold_spans=[GoldSpan.from_dict(s) for s in data.get("gold_spans", [])],
            notes=data.get("notes", ""),
        )


# --------------------------------------------------------------------------- #
# 被测系统的输出
# --------------------------------------------------------------------------- #
@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    text: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrievedChunk:
        return cls(
            chunk_id=str(data.get("chunk_id", "")),
            doc_id=str(data.get("doc_id", "")),
            text=str(data.get("text", "")),
            score=float(data.get("score", 0.0)),
        )


@dataclass
class SystemAnswer:
    text: str
    refused: bool = False
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    trace_id: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["retrieved"] = [c.to_dict() for c in self.retrieved]
        return data


# --------------------------------------------------------------------------- #
# 判分结果
# --------------------------------------------------------------------------- #
@dataclass
class Verdict:
    judged: bool
    correct: bool | None
    refused: bool
    reason: str = ""
    judge: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalScore:
    """k 为评测时的截断位置。gold 无 span 时（不可回答题）全部为 None。"""

    k: int
    span_recall: float | None = None
    hit: bool | None = None
    first_hit_rank: int | None = None
    ndcg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ItemResult:
    item: EvalItem
    answer: SystemAnswer
    verdict: Verdict
    retrieval: RetrievalScore

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.item.id,
            "question": self.item.question,
            "type": self.item.type,
            "answerable": self.item.answerable,
            "gold_answer": self.item.gold_answer,
            "prediction": self.answer.text,
            "prediction_refused": self.answer.refused,
            "verdict": self.verdict.to_dict(),
            "retrieval": self.retrieval.to_dict(),
            "latency_ms": self.answer.latency_ms,
            "prompt_tokens": self.answer.prompt_tokens,
            "completion_tokens": self.answer.completion_tokens,
            "trace_id": self.answer.trace_id,
            "error": self.answer.error,
        }


@dataclass
class EvalReport:
    run_id: str
    started_at: str
    dataset: str
    system: str
    judge: str
    k: int
    summary: dict[str, Any] = field(default_factory=dict)
    by_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    calibration: dict[str, Any] | None = None
    results: list[ItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "dataset": self.dataset,
            "system": self.system,
            "judge": self.judge,
            "k": self.k,
            "summary": self.summary,
            "by_type": self.by_type,
            "calibration": self.calibration,
            "results": [r.to_dict() for r in self.results],
        }
