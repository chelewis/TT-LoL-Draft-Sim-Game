from __future__ import annotations

from fastapi import HTTPException


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def forbidden(detail: str = "You do not have permission to do that.") -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def not_found(detail: str = "Not found.") -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)
