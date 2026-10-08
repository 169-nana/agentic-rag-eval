"""手写种子评测集。

为什么要有它：合成评测集（`eval.generate`）需要配置真实 LLM Key 才能跑，
而**评测框架本身必须先被验证**——否则你无法区分"系统变差了"和"评测器写错了"。

这 16 条是人工编写并核对过的，用来做两件事：
1. 校验 runner / judge / metrics 的计算是否自洽（配合 `--system oracle` 应接近满分）；
2. 作为合成评测集合成后的对照参考（人工写的题通常比模型出的题更"毒"）。

重新生成产物：
    python -m eval.seed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from eval.cli import setup_console
from eval.corpus import load_corpus
from eval.schema import EvalItem, GoldSpan
from eval.validate import validate

logger = logging.getLogger("seed")
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RAW = BACKEND_DIR / "corpus" / "raw"
DEFAULT_OUT = BACKEND_DIR / "eval" / "datasets" / "qa_seed.jsonl"

# 每条：type / question / answer / spans[(语料文件名, 逐字原文片段)] / notes
SEED_ITEMS: list[dict] = [
    # ---------------- 单跳：答案集中在单个片段 ----------------
    {
        "type": "single_hop",
        "question": "星澜科技成立于哪一年？",
        "answer": "2019 年 3 月",
        "spans": [("01-company-overview.md", "星澜科技（Xinglan Tech）成立于 2019 年 3 月，总部位于浙江省杭州市滨江区。")],
        "notes": "事实抽取，答案在句首",
    },
    {
        "type": "single_hop",
        "question": "星澜科技的创始人兼 CEO 是谁？",
        "answer": "陈砚舟",
        "spans": [("01-company-overview.md", "公司创始人兼 CEO 是陈砚舟，他此前在恒远半导体担任首席架构师。")],
        "notes": "人名抽取",
    },
    {
        "type": "single_hop",
        "question": "澜芯 X1 是什么时候正式发布的？",
        "answer": "2022 年 6 月",
        "spans": [("03-products.md", "澜芯 X1 是星澜科技的第一代边缘计算网关，于 2022 年 6 月正式发布。")],
        "notes": "日期抽取，需与文档中其他年份区分",
    },
    {
        "type": "single_hop",
        "question": "澜芯 X2 的整机功耗是多少瓦？",
        "answer": "9 瓦",
        "spans": [("03-products.md", "它将视频接入路数提升到 16 路，整机功耗降低到 9 瓦，并首次支持 5G 模组。")],
        "notes": "数字抽取，且片段中另有一个数字(16路)作干扰",
    },
    {
        "type": "single_hop",
        "question": "恒远半导体总部位于哪座城市？",
        "answer": "江苏省无锡市",
        "spans": [("04-partners.md", "恒远半导体是一家位于江苏省无锡市的芯片设计公司，成立于 2015 年。")],
        "notes": "地名抽取",
    },
    {
        "type": "single_hop",
        "question": "企业版服务等级协议承诺的可用性是多少？",
        "answer": "99.95%",
        "spans": [("05-service-and-pricing.md", "企业版服务等级协议（SLA）承诺 99.95% 的可用性，故障响应时间为 30 分钟。")],
        "notes": "易混淆：同段还有标准版的 99.5%",
    },
    {
        "type": "single_hop",
        "question": "澜图视觉平台提供哪两类预置模型？",
        "answer": "缺陷检测与尺寸测量",
        "spans": [("03-products.md", "该平台提供缺陷检测与尺寸测量两类预置模型，支持私有化部署。")],
        "notes": "指代消解：片段里用「该平台」而没有直呼其名",
    },
    {
        "type": "single_hop",
        "question": "2024 年星澜科技营业收入中，边缘计算网关业务贡献了多少比例？",
        "answer": "62%",
        "spans": [("01-company-overview.md", "其中边缘计算网关业务贡献了 62%")],
        "notes": "同段另有 24% 作干扰",
    },
    # ---------------- 多跳：必须跨两个片段 ----------------
    {
        "type": "multi_hop",
        "question": "澜芯 X1 由哪个团队主导开发？该团队的负责人毕业于哪所大学？",
        "answer": "边缘计算团队；负责人林澈毕业于浙江大学",
        "spans": [
            ("03-products.md", "它由边缘计算团队主导开发，搭载了恒远半导体的 HC-300 边缘推理芯片。"),
            ("02-team-and-people.md", "边缘计算业务线由林澈负责，他于 2019 年 4 月加入星澜科技，毕业于浙江大学控制科学与工程专业。"),
        ],
        "notes": "跨文档桥接：产品 → 团队 → 负责人 → 学历",
    },
    {
        "type": "multi_hop",
        "question": "澜芯 X1 使用的边缘推理芯片由哪家公司提供？该公司总部位于哪座城市？",
        "answer": "恒远半导体，总部位于江苏省无锡市",
        "spans": [
            ("03-products.md", "它由边缘计算团队主导开发，搭载了恒远半导体的 HC-300 边缘推理芯片。"),
            ("04-partners.md", "恒远半导体是一家位于江苏省无锡市的芯片设计公司，成立于 2015 年。"),
        ],
        "notes": "跨文档桥接：产品 → 芯片供应商 → 所在地",
    },
    {
        "type": "multi_hop",
        "question": "星澜科技的 CEO 此前任职的公司，与星澜科技联合开发了哪款芯片？",
        "answer": "HC-300 边缘推理芯片",
        "spans": [
            ("01-company-overview.md", "公司创始人兼 CEO 是陈砚舟，他此前在恒远半导体担任首席架构师。"),
            ("04-partners.md", "双方联合开发了澜芯 X1 所使用的 HC-300 边缘推理芯片。"),
        ],
        "notes": "跨文档桥接：人 → 前雇主 → 合作产物",
    },
    {
        "type": "multi_hop",
        "question": "澜图视觉平台由哪个团队研发？该团队的负责人是什么时候加入星澜科技的？",
        "answer": "工业视觉团队；周牧于 2022 年加入",
        "spans": [
            ("03-products.md", "澜图视觉平台于 2024 年 3 月发布，由工业视觉团队研发。"),
            ("02-team-and-people.md", "工业视觉业务线由周牧负责，他于 2022 年从一家自动驾驶公司加入星澜科技。"),
        ],
        "notes": "跨文档桥接，与上面 X1 那题结构相同，用于检查是否只对特定实体有效",
    },
    {
        "type": "multi_hop",
        "question": "澜芯 X2 相比澜芯 X1，整机功耗降低了多少瓦？",
        "answer": "从 12 瓦降低到 9 瓦，降低了 3 瓦",
        "spans": [
            ("03-products.md", "澜芯 X1 支持 8 路视频接入，整机功耗为 12 瓦。"),
            ("03-products.md", "它将视频接入路数提升到 16 路，整机功耗降低到 9 瓦，并首次支持 5G 模组。"),
        ],
        "notes": "同文档比较型多跳：需要同时看两处并做减法",
    },
    # ---------------- 不可回答：正确答案是「资料不足」 ----------------
    {
        "type": "unanswerable",
        "question": "星澜科技 2023 年的营业收入是多少？",
        "answer": None,
        "spans": [],
        "notes": "语料只有 2024 年营收，年份被替换 → 测试模型会不会拿 8.7 亿硬套",
    },
    {
        "type": "unanswerable",
        "question": "澜芯 X3 网关的发布时间是什么时候？",
        "answer": None,
        "spans": [],
        "notes": "产品线里只有 X1/X2，X3 不存在 → 测试模型会不会编造发布日期",
    },
    {
        "type": "unanswerable",
        "question": "星澜科技在深圳是否设有研发中心？",
        "answer": None,
        "spans": [],
        "notes": "语料只提到杭州总部 → 测试模型会不会把总部信息外推",
    },
]

ID_PREFIX = {"single_hop": "sh", "multi_hop": "mh", "unanswerable": "un"}


def build_items(raw_dir: Path) -> list[EvalItem]:
    docs = load_corpus(raw_dir)
    doc_id_by_file = {doc.path.relative_to(raw_dir).as_posix(): doc.doc_id for doc in docs}

    counters: Counter[str] = Counter()
    items: list[EvalItem] = []

    for spec in SEED_ITEMS:
        item_type = spec["type"]
        counters[item_type] += 1
        item_id = f"{ID_PREFIX[item_type]}-{counters[item_type]:03d}"

        spans: list[GoldSpan] = []
        for filename, span_text in spec["spans"]:
            doc_id = doc_id_by_file.get(filename)
            if doc_id is None:
                raise KeyError(f"{item_id} 引用了不存在的语料文件：{filename}")
            spans.append(GoldSpan(doc_id=doc_id, text=span_text))

        items.append(
            EvalItem(
                id=item_id,
                question=spec["question"],
                type=item_type,
                answerable=item_type != "unanswerable",
                gold_answer=spec["answer"],
                gold_spans=spans,
                notes=spec.get("notes", ""),
            )
        )
    return items


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description="生成手写种子评测集并自动校验")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    items = build_items(args.raw)

    problems, stats = validate(items, args.raw)
    if problems:
        logger.error("种子评测集自校验未通过：")
        for problem in problems:
            logger.error("  %s", problem)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fp:
        for item in items:
            fp.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    logger.info("已写入 %s", args.out)
    logger.info("统计：%s", stats["by_type"])
    logger.info("自校验通过：所有 gold 片段都能在原文中逐字定位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
