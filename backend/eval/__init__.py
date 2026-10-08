"""评测框架。

放在 `eval/` 下，用 `python -m eval.run_eval` 调用。
注意：`eval` 与 Python 内置函数 eval 同名，但内置 eval 是函数不是模块，
不存在导入冲突。如果你更在意可读性，重命名为 rag_eval 也可以，
只需同步修改各文件里的 `from eval... import`。
"""

from __future__ import annotations
