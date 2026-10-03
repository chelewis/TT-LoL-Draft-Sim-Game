"""Errors from the Riot integration. Messages are written to be shown to users."""
from __future__ import annotations


class RiotError(Exception):
    status_code = 502

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RiotNotConfigured(RiotError):
    status_code = 503


class RiotNotFound(RiotError):
    status_code = 404


class RiotAuthError(RiotError):
    """The API key is missing, invalid or expired (development keys expire every 24 hours)."""
    status_code = 503


class RiotRateLimited(RiotError):
    status_code = 429


class RiotUnavailable(RiotError):
    status_code = 502


class NotEnoughData(RiotError):
    status_code = 422
