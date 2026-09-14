"""Shared FastAPI dependencies."""

from fastapi import Request

from session import SolarSession


def get_session(request: Request) -> SolarSession:
    return request.app.state.session


def get_inverter(request: Request):
    """The background inverter reader (inverter.reader.InverterReader, or the mock one)."""
    return request.app.state.inverter
