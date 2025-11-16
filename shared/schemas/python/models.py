from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: str = Field(..., min_length=1)
    email: Optional[EmailStr] = None
    roles: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None


class Profile(BaseModel):
    user_id: str = Field(..., min_length=1)
    nickname: Optional[str] = None
    mood: Optional[str] = None
    discord_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Reflection(BaseModel):
    id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    date: datetime
    reflection: str
    mantra: Optional[str] = None
    villain: Optional[str] = None
    future_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Trade(BaseModel):
    id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    instrument: str
    direction: Literal["long", "short"]
    entry_price: float
    exit_price: Optional[float] = None
    result: Optional[Literal["win", "loss", "breakeven"]] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None


class Insight(BaseModel):
    id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    source: Literal["reflection", "trade", "system"]
    summary: str
    tags: List[str] = Field(default_factory=list)
    created_at: datetime


class VisionBlueprint(BaseModel):
    id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    date: date
    vision_text: str


__all__ = [
    "User",
    "Profile",
    "Reflection",
    "Trade",
    "Insight",
    "VisionBlueprint",
]
