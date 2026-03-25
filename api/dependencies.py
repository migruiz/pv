"""Shared FastAPI dependencies."""

from fastapi import Request

from session import SolarSession


def get_session(request: Request) -> SolarSession:
    return request.app.state.session
