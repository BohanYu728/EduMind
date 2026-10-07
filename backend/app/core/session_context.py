"""请求作用域。没有标识的旧客户端只访问归档资料，不跨会话查询。"""

from contextvars import ContextVar

session_scope: ContextVar[str | None] = ContextVar("edumind_session", default=None)


def current_session_id() -> str:
    return session_scope.get() or "legacy"
