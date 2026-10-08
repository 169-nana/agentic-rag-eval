"""数据库连接。

把"怎么连数据库"收在一个文件里。以后要是换了数据库（比如切回 SQLite），
只需要改这里，其他文件都不动。

这就和 llm/ 那一层是同一个思路：把"会变的东西"隔离开。
"""

import psycopg

from app.config import get_settings


def connect() -> psycopg.Connection:
    """建立一个数据库连接。

    用法：
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    ⚠ 关于上面的 with：psycopg 的连接对象在 with 块结束时——
       正常退出就自动 commit（提交），抛异常就自动 rollback（回滚）。
       这意味着整个块里的操作要么全成功、要么全撤销，
       不会出现"文档存进去了但片段没存"这种半截状态。
       这叫【事务】，是数据库保证数据一致性的核心机制。
    """
    return psycopg.connect(get_settings().database_url)