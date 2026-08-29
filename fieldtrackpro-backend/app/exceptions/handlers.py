import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.exceptions.custom import BaseAPIException

logger = logging.getLogger("fieldtrackpro")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BaseAPIException)
    async def base_api_exception_handler(request: Request, exc: BaseAPIException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": str(exc.error_code),
                    "message": exc.detail,
                    "details": exc.details if exc.details is not None else None,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
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
        headers = exc.headers if hasattr(exc, "headers") and exc.headers else None
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": str(exc.detail) if exc.detail else "An error occurred",
                    "details": None,
                }
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
        sanitized_details = []
        for err in exc.errors():
            err_dict = dict(err)
            if "ctx" in err_dict:
                err_dict["ctx"] = {k: str(v) for k, v in err_dict["ctx"].items()}
            sanitized_details.append(err_dict)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request payload or parameters",
                    "details": sanitized_details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.url.path}: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred.",
                    "details": None,
                }
            },
        )
