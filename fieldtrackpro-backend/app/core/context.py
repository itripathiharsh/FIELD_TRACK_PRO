import contextvars

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


def get_current_request_id() -> str:
    """Return the active correlation request ID for this async context, or empty string."""
    return request_id_ctx.get("")


def set_current_request_id(request_id: str) -> contextvars.Token:
    """Set the active request ID in context."""
    return request_id_ctx.set(request_id)


def get_current_user_id() -> str:
    """Return the authenticated user ID for this async context, or empty string."""
    return user_id_ctx.get("")


def set_current_user_id(user_id: str) -> contextvars.Token:
    """Set the active user ID in context."""
    return user_id_ctx.set(user_id)
