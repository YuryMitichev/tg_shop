import contextvars

_shop_id_ctx: contextvars.ContextVar[int] = contextvars.ContextVar("shop_id", default=1)


def get_shop_id() -> int:
    return _shop_id_ctx.get()
