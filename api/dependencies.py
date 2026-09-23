"""Shared FastAPI dependencies."""

from fastapi import Request


def get_inverter(request: Request):
    """The background inverter reader (inverter.reader.InverterReader)."""
    return request.app.state.inverter
