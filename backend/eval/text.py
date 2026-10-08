"""文本匹配工具。

中文没有天然词边界，这里一律退到**字符 n-gram**（默认 bigram），
不引入分词依赖，保证评测脚本在任何环境都能跑。
"""

from __future__ import annotations

import re
from collections import Counter
from unicodedata import normalize as unicodedata_normalize

_PUNCT = re.compile(
    r"[\s\u3000·，。、；：？！\"'“”‘’（）()《》〈〉【】\[\]{}—–\-…,.!?;:/\\|~`@#$%^&*+=_<>]+"
)


def normalize_text(text: str) -> str:
    """全角转半角、转小写、去标点空白。用于所有文本比对。"""
    return _PUNCT.sub("", unicodedata_normalize("NFKC", text).lower())


def char_ngrams(text: str, n: int = 2) -> list[str]:
    text = normalize_text(text)
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def f1(prediction: str, gold: str, n: int = 2) -> float:
    """字符 n-gram F1。用作规则判分器的兜底相似度。"""
    pred_grams = Counter(char_ngrams(prediction, n))
    gold_grams = Counter(char_ngrams(gold, n))
    if not pred_grams or not gold_grams:
        return 0.0
    overlap = sum((pred_grams & gold_grams).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(pred_grams.values())
    recall = overlap / sum(gold_grams.values())
    return 2 * precision * recall / (precision + recall)


def coverage(span: str, container: str, n: int = 2) -> float:
    """span 的字符 n-gram 有多大比例出现在 container 里。

    这是判断"检索到的片段是否覆盖了 gold 原文"的核心函数。
    用 coverage 而不是 F1，是因为 container（整个 chunk）通常远长于 span，
    F1 会被 container 的长度稀释，导致明明命中了却算不中。
    """
    span_grams = Counter(char_ngrams(span, n))
    if not span_grams:
        return 0.0
    container_grams = Counter(char_ngrams(container, n))
    return sum((span_grams & container_grams).values()) / sum(span_grams.values())


def is_covered(span: str, container: str, threshold: float = 0.92) -> bool:
    """先做精确包含的快速判断，再做模糊覆盖，兼顾速度与鲁棒。"""
    needle = normalize_text(span)
    if needle and needle in normalize_text(container):
        return True
    return coverage(span, container) >= threshold


def locate_span(text: str, evidence: str, threshold: float = 0.85) -> str | None:
    """在 text 中定位 evidence 对应的原文区间。

    出题时模型经常"记得住意思、引不准原话"，直接丢弃太浪费，
    但 gold span 必须是逐字原文（否则检索覆盖度判定会失效）。
    所以这里用滑动窗口找回最接近的一段原文，找不回就返回 None 让调用方丢弃。
    """
    evidence = evidence.strip()
    if not evidence:
        return None
    if evidence in text:
        return evidence

    window = len(evidence)
    best_score = 0.0
    best_start = -1
    for start in range(0, max(len(text) - window + 1, 0)):
        score = coverage(evidence, text[start : start + window])
        if score > best_score:
            best_score, best_start = score, start
            if score >= 0.999:
                break

    if best_start < 0 or best_score < threshold:
        return None
    # 稍微外扩一点，避免把原文切成半个词
    start = max(0, best_start - 8)
    end = min(len(text), best_start + window + 8)
    return text[start:end].strip()


def truncate(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
