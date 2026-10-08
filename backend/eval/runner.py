"""评测执行器：把数据集跑过被测系统，逐条判分并算指标。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from eval import metrics
from eval.judges import Judge
from eval.schema import EvalItem, EvalReport, ItemResult
from eval.systems import SystemUnderTest

logger = logging.getLogger(__name__)


def load_dataset(path: Path) -> list[EvalItem]:
    items: list[EvalItem] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            items.append(EvalItem.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"{path} 第 {lineno} 行不是合法的评测项: {exc}") from exc

    if not items:
        raise ValueError(f"{path} 中没有评测项")
    return items


async def run_eval(
    items: list[EvalItem],
    system: SystemUnderTest,
    judge: Judge,
    *,
    dataset_name: str,
    k: int = 5,
    concurrency: int = 4,
    price_in_per_1m: float = 0.0,
    price_out_per_1m: float = 0.0,
    progress_every: int = 10,
) -> EvalReport:
    semaphore = asyncio.Semaphore(concurrency)
    done = 0
    total = len(items)
    results: list[ItemResult] = []
    lock = asyncio.Lock()

    async def one(item: EvalItem) -> ItemResult:
        nonlocal done
        async with semaphore:
            answer = await system.answer(item)
            try:
                verdict = await judge.judge(item, answer)
            except Exception as exc:  # noqa: BLE001
                logger.exception("判分异常 id=%s", item.id)
                from eval.schema import Verdict

                verdict = Verdict(
                    judged=False, correct=None, refused=answer.refused,
                    reason=f"判分异常: {exc}", judge=getattr(judge, "name", "?"),
                )

            result = ItemResult(
                item=item,
                answer=answer,
                verdict=verdict,
                retrieval=metrics.score_retrieval(item, answer, k=k),
            )

        async with lock:
            done += 1
            if progress_every and (done % progress_every == 0 or done == total):
                logger.info("评测进度 %d/%d", done, total)
        return result

    # return_exceptions=False：单条内部已经兜住异常，这里不需要再吞
    results = list(await asyncio.gather(*(one(item) for item in items)))

    summary = metrics.aggregate(
        results, price_in_per_1m=price_in_per_1m, price_out_per_1m=price_out_per_1m
    )
    by_type = metrics.aggregate_by_type(
        results, price_in_per_1m=price_in_per_1m, price_out_per_1m=price_out_per_1m
    )

    return EvalReport(
        run_id=uuid.uuid4().hex[:12],
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        dataset=dataset_name,
        system=system.name,
        judge=getattr(judge, "name", "?"),
        k=k,
        summary=summary,
        by_type=by_type,
        results=results,
    )
