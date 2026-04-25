from __future__ import annotations

from typing import Protocol

from utils.settings_service import SettingsService


class AlphapyBot(Protocol):
    start_time: float
    settings: SettingsService
