"""CLI 公共初始化。

Windows 的默认控制台编码常常是 GBK，直接 print 中文以外的符号（✅ 之类）
会抛 UnicodeEncodeError 把脚本打断。所有入口统一走这里，
把 stdout/stderr 切到 UTF-8 并容错，同时统一日志格式。
"""

from __future__ import annotations

import logging
import sys


def setup_console(level: int = logging.INFO) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            # 被重定向成非 TextIOWrapper（如测试框架捕获）时忽略
            pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
