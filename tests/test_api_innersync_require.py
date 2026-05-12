"""Tests for api._require_discord_id_for_linked_innersync (403 / success paths)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import api as api_module


@pytest.mark.asyncio
async def test_require_discord_raises_403_when_unlinked() -> None:
    pool = MagicMock()
    with (
        patch.object(api_module, "db_pool", pool),
        patch(
            "utils.innersync_identity.resolve_innersync_jwt_sub_to_discord_int",
            new=AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as ei:
            await api_module._require_discord_id_for_linked_innersync(
                "550e8400-e29b-41d4-a716-446655440000"
            )
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_require_discord_returns_int_when_linked() -> None:
    pool = MagicMock()
    with (
        patch.object(api_module, "db_pool", pool),
        patch(
            "utils.innersync_identity.resolve_innersync_jwt_sub_to_discord_int",
            new=AsyncMock(return_value=777888),
        ),
    ):
        out = await api_module._require_discord_id_for_linked_innersync(
            "550e8400-e29b-41d4-a716-446655440000"
        )
    assert out == 777888
