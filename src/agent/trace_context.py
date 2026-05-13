from contextvars import ContextVar
from uuid import uuid4

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    return trace_id_var.get()


def set_trace_id(tid: str) -> ContextVar[str]:
    return trace_id_var.set(tid)


def generate_trace_id() -> str:
    return str(uuid4())
