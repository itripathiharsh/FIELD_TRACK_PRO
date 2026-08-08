class BaseAPIException(Exception):
    """Base exception class for API errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = 400,
        error_code: str = "API_ERROR",
        # legacy alias
        message: str | None = None,
    ):
        self.detail = detail or message or "An error occurred"
        self.message = self.detail   # backwards-compat
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.detail)


class ResourceNotFoundException(BaseAPIException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail=detail, status_code=404, error_code="RESOURCE_NOT_FOUND")


class UnauthorizedException(BaseAPIException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(detail=detail, status_code=401, error_code="UNAUTHORIZED")


class ForbiddenException(BaseAPIException):
    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(detail=detail, status_code=403, error_code="FORBIDDEN")


class ValidationException(BaseAPIException):
    def __init__(self, detail: str = "Validation failed"):
        super().__init__(detail=detail, status_code=422, error_code="VALIDATION_ERROR")


class DuplicateResourceException(BaseAPIException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(detail=detail, status_code=409, error_code="DUPLICATE_RESOURCE")


class InvalidStateTransitionException(BaseAPIException):
    def __init__(self, detail: str = "Invalid state transition"):
        super().__init__(detail=detail, status_code=422, error_code="INVALID_STATE_TRANSITION")

