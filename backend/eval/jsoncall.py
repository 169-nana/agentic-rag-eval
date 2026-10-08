"""JSON 调用工具（兼容层）。

实现已经搬到 `app/jsoncall.py` —— 因为它是产品代码，不只是评测代码。
（层级应该是 app 被 eval 依赖，而不是反过来。）

这个文件保留下来只是为了让老的 `from eval.jsoncall import ...` 继续可用。
新代码请直接 `from app.jsoncall import call_json`。
"""

from app.jsoncall import DEFAULT_SYSTEM, JsonParseError, call_json, extract_json

__all__ = ["DEFAULT_SYSTEM", "JsonParseError", "call_json", "extract_json"]
