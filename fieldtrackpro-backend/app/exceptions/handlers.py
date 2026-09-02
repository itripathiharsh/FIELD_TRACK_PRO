import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.context import get_current_request_id, get_current_user_id
from app.exceptions.custom import BaseAPIException

logger = logging.getLogger("fieldtrackpro")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BaseAPIException)
    async def base_api_exception_handler(request: Request, exc: BaseAPIException):
        req_id = get_current_request_id() or getattr(request.state, "request_id", "-")
        uid = get_current_user_id() or getattr(request.state, "user_id", None) or "-"
        logger.warning(
            "event=api_error request_id=%s method=%s path=%s status=%s error_code=%s detail=%s user_id=%s",
            req_id,
            request.method,
            request.url.path,
            exc.status_code,
            exc.error_code,
            exc.detail,
            uid,
        )
        headers = {"X-Request-ID": req_id} if req_id != "-" else {}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": str(exc.error_code),
                    "message": exc.detail,
                    "details": exc.details if exc.details is not None else None,
                    "request_id": req_id,
                }
            },
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        req_id = get_current_request_id() or getattr(request.state, "request_id", "-")
        uid = get_current_user_id() or getattr(request.state, "user_id", None) or "-"
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "RESOURCE_NOT_FOUND",
            409: "DUPLICATE_RESOURCE",
            422: "VALIDATION_ERROR",
            429: "TOO_MANY_REQUESTS",
            500: "INTERNAL_SERVER_ERROR",
        }
        error_code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        headers = dict(exc.headers) if hasattr(exc, "headers") and exc.headers else {}
        if req_id != "-":
            headers["X-Request-ID"] = req_id

        logger.warning(
            "event=http_error request_id=%s method=%s path=%s status=%s error_code=%s detail=%s user_id=%s",
            req_id,
            request.method,
            request.url.path,
            exc.status_code,
            error_code,
            str(exc.detail) if exc.detail else "An error occurred",
            uid,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": str(exc.detail) if exc.detail else "An error occurred",
                    "details": None,
                    "request_id": req_id,
                }
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = get_current_request_id() or getattr(request.state, "request_id", "-")
        uid = get_current_user_id() or getattr(request.state, "user_id", None) or "-"
        sanitized_details = []
        for err in exc.errors():
            err_dict = dict(err)
            if "ctx" in err_dict:
                err_dict["ctx"] = {k: str(v) for k, v in err_dict["ctx"].items()}
            sanitized_details.append(err_dict)

        logger.warning(
            "event=validation_error request_id=%s method=%s path=%s status=422 errors=%s user_id=%s",
            req_id,
            request.method,
            request.url.path,
            sanitized_details,
            uid,
        )

        headers = {"X-Request-ID": req_id} if req_id != "-" else {}
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request payload or parameters",
                    "details": sanitized_details,
                    "request_id": req_id,
                }
            },
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        req_id = get_current_request_id() or getattr(request.state, "request_id", "-")
        uid = get_current_user_id() or getattr(request.state, "user_id", None) or "-"
        logger.error(
            "event=unhandled_exception request_id=%s method=%s path=%s user_id=%s exception=%s: %s",
            req_id,
            request.method,
            request.url.path,
            uid,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        headers = {"X-Request-ID": req_id} if req_id != "-" else {}
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred.",
                    "details": None,
                    "request_id": req_id,
                }
            },
            headers=headers,
        )
