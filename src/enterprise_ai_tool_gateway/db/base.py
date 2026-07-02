"""SQLAlchemy declarative base for gateway persistence."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for Stage 4 persistence models."""
