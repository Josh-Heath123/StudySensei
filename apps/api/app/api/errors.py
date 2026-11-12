"""Map service errors to HTTP responses with a plain ``{"detail": "..."}`` body."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.errors import Conflict, Invalid, NotFound

STATUS_FOR: dict[type[Exception], int] = {
    NotFound: status.HTTP_404_NOT_FOUND,
    Conflict: status.HTTP_409_CONFLICT,
    Invalid: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _service_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=STATUS_FOR[type(exc)])


def add_error_handlers(app: FastAPI) -> None:
    for error in STATUS_FOR:
        app.add_exception_handler(error, _service_error)
