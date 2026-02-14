"""
Tests for /config start setup wizard: SETUP_STEPS, SetupWizardView helpers, resolved data.
No full Discord environment; uses mocks for interaction and cog.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from cogs.configuration import (
    SETUP_STEPS,
    SetupStep,
    SetupWizardView,
)


class TestSetupSteps:
    """SETUP_STEPS list and SetupStep structure."""

    def test_setup_steps_has_eight_steps(self):
        assert len(SETUP_STEPS) == 8

    def test_first_step_is_log_channel(self):
        step = SETUP_STEPS[0]
        assert step.scope == "system"
        assert step.key == "log_channel_id"
        assert step.value_type == "channel"
        assert "log" in step.label.lower()

    def test_last_step_is_staff_role(self):
        step = SETUP_STEPS[-1]
        assert step.scope == "ticketbot"
        assert step.key == "staff_role_id"
        assert step.value_type == "role"

    def test_all_value_types_valid(self):
        allowed = {"channel", "channel_category", "role"}
        for step in SETUP_STEPS:
            assert step.value_type in allowed, f"Invalid value_type: {step.value_type}"

    def test_ticketbot_category_is_channel_category(self):
        category_step = next(s for s in SETUP_STEPS if s.key == "category_id" and s.scope == "ticketbot")
        assert category_step.value_type == "channel_category"


class TestSetupWizardView:
    """SetupWizardView: step index, embed builders, same-user check, resolved data."""

    @pytest.fixture
    def mock_cog(self):
        cog = MagicMock()
        cog.settings = MagicMock()
        cog.settings.set = AsyncMock(return_value=None)
        cog._send_audit_log = AsyncMock(return_value=None)
        return cog

    def _view(self, mock_cog):
        """Create view inside async test so discord.ui.View has a running event loop."""
        return SetupWizardView(
            cog=mock_cog,
            guild_id=999,
            user_id=111,
            steps=SETUP_STEPS,
        )

    @pytest.mark.asyncio
    async def test_current_step_first(self, mock_cog):
        view = self._view(mock_cog)
        assert view.step_index == 0
        step = view._current_step()
        assert step is not None
        assert step.scope == "system"
        assert step.key == "log_channel_id"

    @pytest.mark.asyncio
    async def test_current_step_after_all_returns_none(self, mock_cog):
        view = self._view(mock_cog)
        view.step_index = len(SETUP_STEPS)
        assert view._current_step() is None

    @pytest.mark.asyncio
    async def test_build_step_embed_title_and_footer(self, mock_cog):
        view = self._view(mock_cog)
        step = view._current_step()
        embed = view._build_step_embed(step)
        assert "step 1 of 8" in embed.title.lower()
        assert "Server setup" in embed.title
        assert step.label in embed.description
        assert "Skip" in embed.description
        assert "1/8" in embed.footer.text

    @pytest.mark.asyncio
    async def test_build_step_embed_step_two(self, mock_cog):
        view = self._view(mock_cog)
        view.step_index = 1
        step = view._current_step()
        embed = view._build_step_embed(step)
        assert "step 2 of 8" in embed.title.lower()
        assert "2/8" in embed.footer.text

    @pytest.mark.asyncio
    async def test_build_complete_embed_empty_session(self, mock_cog):
        view = self._view(mock_cog)
        embed = view._build_complete_embed()
        assert "Setup complete" in embed.title
        assert "config start" in embed.footer.text
        assert len(embed.fields) == 0

    @pytest.mark.asyncio
    async def test_build_complete_embed_with_configured(self, mock_cog):
        view = self._view(mock_cog)
        view.configured_in_session.append(("Log channel", "#logs"))
        view.configured_in_session.append(("Rules channel", "#rules"))
        embed = view._build_complete_embed()
        assert len(embed.fields) == 1
        assert "Configured" in embed.fields[0].name
        assert "**Log channel**" in embed.fields[0].value
        assert "#logs" in embed.fields[0].value
        assert "**Rules channel**" in embed.fields[0].value
        assert "#rules" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_build_complete_embed_shows_skipped(self, mock_cog):
        view = self._view(mock_cog)
        view.configured_in_session.append(("Log channel", "#logs"))
        view.configured_in_session.append(("Rules channel", "— Skipped"))
        embed = view._build_complete_embed()
        assert len(embed.fields) == 1
        assert "**Log channel**" in embed.fields[0].value
        assert "#logs" in embed.fields[0].value
        assert "**Rules channel**" in embed.fields[0].value
        assert "— Skipped" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_build_timeout_embed(self, mock_cog):
        view = self._view(mock_cog)
        embed = view._build_timeout_embed()
        assert "timed out" in embed.title.lower()
        assert "/config start" in embed.description

    @pytest.mark.asyncio
    async def test_ensure_same_user_true(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.user.id = 111
        assert view._ensure_same_user(interaction) is True

    @pytest.mark.asyncio
    async def test_ensure_same_user_false(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.user.id = 999
        assert view._ensure_same_user(interaction) is False

    @pytest.mark.asyncio
    async def test_get_resolved_channels_from_dict(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        channel = MagicMock()
        channel.id = 12345
        # Object-style (like Discord ComponentInteractionData); dict.values would be the dict method
        interaction.data = MagicMock()
        interaction.data.values = ["12345"]
        interaction.data.resolved = MagicMock()
        interaction.data.resolved.channels = {"12345": channel}
        interaction.guild.get_channel = MagicMock(return_value=None)
        result = view._get_resolved_channels(interaction)
        assert result is not None
        assert result.id == 12345

    @pytest.mark.asyncio
    async def test_get_resolved_channels_from_dict_data(self, mock_cog):
        """When interaction.data is a dict (e.g. from Discord), use .get('values') not getattr (dict.values is the method)."""
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        channel = MagicMock()
        channel.id = 99999
        interaction.data = {
            "values": ["99999"],
            "resolved": {"channels": {"99999": channel}},
        }
        interaction.guild.get_channel = MagicMock(return_value=None)
        result = view._get_resolved_channels(interaction)
        assert result is not None
        assert result.id == 99999

    @pytest.mark.asyncio
    async def test_get_resolved_channels_missing_data_returns_none(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.data = {}
        assert view._get_resolved_channels(interaction) is None

    @pytest.mark.asyncio
    async def test_get_resolved_channels_invalid_value_returns_none(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.data = {"values": ["not-a-number"], "resolved": {"channels": {}}}
        assert view._get_resolved_channels(interaction) is None

    @pytest.mark.asyncio
    async def test_get_resolved_role_from_dict(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        role = MagicMock()
        role.id = 67890
        # Object-style (like Discord ComponentInteractionData)
        interaction.data = MagicMock()
        interaction.data.values = ["67890"]
        interaction.data.resolved = MagicMock()
        interaction.data.resolved.roles = {"67890": role}
        interaction.guild.get_role = MagicMock(return_value=None)
        result = view._get_resolved_role(interaction)
        assert result is not None
        assert result.id == 67890

    @pytest.mark.asyncio
    async def test_get_resolved_role_missing_data_returns_none(self, mock_cog):
        view = self._view(mock_cog)
        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.data = {}
        assert view._get_resolved_role(interaction) is None
