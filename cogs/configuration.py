from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple, cast
import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.validators import validate_admin
from utils.fyi_tips import FYI_KEYS as FYI_TIPS_KEYS
from utils.db_helpers import acquire_safe
from utils.embed_builder import EmbedBuilder
from utils.settings_service import SettingsService, SettingDefinition
from utils.automod_rules import RuleProcessor, RuleType, ActionType
from utils.premium_guard import guild_has_premium
from utils.logger import log_with_guild, log_guild_action, logger
from utils.sanitizer import safe_embed_text
from utils.timezone import BRUSSELS_TZ
from cogs.reaction_roles import StartOnboardingView
from utils.cog_base import AlphaCog
from cogs.configuration_ui import SetupStep, SETUP_STEPS, SetupWizardView, ReorderQuestionsModal
from cogs.configuration_automod import (
    normalize_automod_action_type,
    is_advanced_action,
    check_advanced_action_premium,
    validate_rule_update_fields,
)
def requires_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        is_admin, _ = await validate_admin(interaction, raise_on_fail=False)
        if is_admin:
            return True
        raise app_commands.CheckFailure("You need administrator permissions for this command.")
    return app_commands.check(predicate)
class Configuration(AlphaCog):
    config = app_commands.Group(
        name="config",
        description="Manage bot settings",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )
    system_group = app_commands.Group(
        name="system",
        description="System settings",
        parent=config,
    )
    embedwatcher_group = app_commands.Group(
        name="embedwatcher",
        description="Embed watcher settings",
        parent=config,
    )
    ticketbot_group = app_commands.Group(
        name="ticketbot",
        description="TicketBot settings",
        parent=config,
    )
    gpt_group = app_commands.Group(
        name="gpt",
        description="Grok / AI settings",
        parent=config,
    )
    invites_group = app_commands.Group(
        name="invites",
        description="Invite tracker settings",
        parent=config,
    )
    reminders_group = app_commands.Group(
        name="reminders",
        description="Reminder settings",
        parent=config,
    )
    gdpr_group = app_commands.Group(
        name="gdpr",
        description="GDPR settings",
        parent=config,
    )
    onboarding_group = app_commands.Group(
        name="onboarding",
        description="Onboarding configuration",
        parent=config,
    )
    fyi_group = app_commands.Group(
        name="fyi",
        description="Contextual FYI tips (admin testing)",
        parent=config,
    )
    verification_group = app_commands.Group(
        name="verification",
        description="Verification settings",
        parent=config,
    )
    automod_group = app_commands.Group(
        name="automod",
        description="Auto-moderation settings",
        parent=config,
    )
    growth_group = app_commands.Group(
        name="growth",
        description="Growth Check-in settings",
        parent=config,
    )
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.rule_processor = RuleProcessor(bot)

        # Validate database pool availability
        from utils.db_helpers import get_bot_db_pool
        if get_bot_db_pool(bot) is None:
            from utils.logger import logger
            logger.warning("⚠️ Database pool not available - auto-moderation features will be limited")

    @config.command(name="scopes", description="Show all available setting scopes")
    @requires_admin()
    async def config_scopes(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        scopes = self.settings.scopes()
        if not scopes:
            await interaction.followup.send("⚠️ No scopes registered.", ephemeral=True)
            return
        lines = ["📁 **Available scopes**:"]
        lines.extend(f"• `{scope}`" for scope in scopes)
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @config.command(
        name="start",
        description="Start the interactive server setup (choose or skip channel/role per step)",
    )
    @requires_admin()
    async def config_start(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command only works in a server.",
                ephemeral=True,
            )
            return
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        view = SetupWizardView(cog=self, guild_id=guild_id, user_id=user_id, steps=SETUP_STEPS)
        first_step = view._current_step()
        if not first_step:
            await interaction.response.send_message(
                "⚠️ No setup steps defined.",
                ephemeral=True,
            )
            return
        embed = view._build_step_embed(first_step)
        view._clear_and_add_components(first_step)
        message = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = cast(Any, message)
        log_with_guild(f"Setup wizard started (guild_id={guild_id}, user_id={user_id})", guild_id, "debug")

    @fyi_group.command(name="reset", description="Clear an FYI flag so the next trigger will send again (testing)")
    @app_commands.choices(key=[app_commands.Choice(name=k, value=k) for k in sorted(FYI_TIPS_KEYS)])
    @requires_admin()
    async def fyi_reset(
        self,
        interaction: discord.Interaction,
        key: str,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        from utils.fyi_tips import reset_fyi
        if key not in FYI_TIPS_KEYS:
            await interaction.response.send_message(f"❌ Unknown FYI key: `{key}`. Use one of: {', '.join(sorted(FYI_TIPS_KEYS))}.", ephemeral=True)
            return
        ok = await reset_fyi(self.bot, interaction.guild.id, key)
        if ok:
            await interaction.response.send_message(f"✅ FYI flag `{key}` cleared. The next time that event happens, the tip will be sent again.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Could not clear `{key}`.", ephemeral=True)

    @fyi_group.command(name="send", description="Force-send an FYI now (testing)")
    @app_commands.choices(key=[app_commands.Choice(name=k, value=k) for k in sorted(FYI_TIPS_KEYS)])
    @requires_admin()
    async def fyi_send(
        self,
        interaction: discord.Interaction,
        key: str,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from utils.fyi_tips import force_send_fyi
        if key not in FYI_TIPS_KEYS:
            await interaction.followup.send(f"❌ Unknown FYI key: `{key}`. Use one of: {', '.join(sorted(FYI_TIPS_KEYS))}.", ephemeral=True)
            return
        sent = await force_send_fyi(self.bot, interaction.guild.id, key, mark_as_sent=True)
        if sent:
            await interaction.followup.send(f"✅ FYI `{key}` sent to the log channel (and marked as sent).", ephemeral=True)
        else:
            await interaction.followup.send("❌ Could not send (e.g. no log channel set or channel not found).", ephemeral=True)

    @system_group.command(name="show", description="Show system settings")
    @requires_admin()
    async def system_show(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by the check above
        items = self.settings.list_scope("system", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No system settings registered.", ephemeral=True)
            return
        lines = ["🛠️ **System settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @system_group.command(name="set_log_channel", description="Set the log channel")
    @requires_admin()
    async def system_set_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("system", "log_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Log channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting updated",
            f"`system.log_channel_id` set to {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_log_channel", description="Reset log channel to default value")
    @requires_admin()
    async def system_reset_log_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "log_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "log_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Log channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting reset",
            f"`system.log_channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="set_rules_channel", description="Set the rules and onboarding channel (welcome + Start button)")
    @requires_admin()
    async def system_set_rules_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("system", "rules_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Rules channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting updated",
            f"`system.rules_channel_id` set to {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_rules_channel", description="Reset rules and onboarding channel to default value")
    @requires_admin()
    async def system_reset_rules_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "rules_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "rules_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Rules channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting reset",
            f"`system.rules_channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="set_log_level", description="Set log verbosity level")
    @requires_admin()
    @app_commands.choices(level=[
        app_commands.Choice(name="Verbose - All logs", value="verbose"),
        app_commands.Choice(name="Normal - No debug", value="normal"),
        app_commands.Choice(name="Critical - Errors + config only", value="critical"),
    ])
    async def system_set_log_level(
        self,
        interaction: discord.Interaction,
        level: app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("system", "log_level", level.value, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Log level set to **{level.name}**.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting updated",
            f"`system.log_level` set to `{level.value}` by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_log_level", description="Reset log level to default (verbose)")
    @requires_admin()
    async def system_reset_log_level(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "log_level", interaction.guild.id, interaction.user.id)
        default_level = self.settings.get("system", "log_level", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Log level reset to default: **{default_level}**.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting reset",
            f"`system.log_level` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="show", description="Show embed watcher settings")
    @requires_admin()
    async def embedwatcher_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("embedwatcher", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No embed watcher settings found.", ephemeral=True)
            return
        lines = ["📣 **Embed watcher settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @embedwatcher_group.command(name="set_announcements", description="Choose the channel to monitor")
    @requires_admin()
    async def embedwatcher_set_announcements(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("embedwatcher", "announcements_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Announcement channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` → {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="reset_announcements", description="Reset announcement channel to default")
    @requires_admin()
    async def embedwatcher_reset_announcements(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "announcements_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("embedwatcher", "announcements_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Announcement channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="set_offset", description="Set reminder offset (minutes)")
    @requires_admin()
    async def embedwatcher_set_offset(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 0, 4320],
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("embedwatcher", "reminder_offset_minutes", minutes, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Reminder offset set to {minutes} minutes.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` → {minutes} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="reset_offset", description="Reset reminder offset to default")
    @requires_admin()
    async def embedwatcher_reset_offset(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "reminder_offset_minutes", interaction.guild.id, interaction.user.id)
        default_minutes = self.settings.get("embedwatcher", "reminder_offset_minutes", interaction.guild.id)
        await interaction.followup.send(
            f"✅ Reminder offset reset to default: {default_minutes} minutes.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    
    @embedwatcher_group.command(name="set_non_embed", description="Enable/disable non-embed message parsing")
    @requires_admin()
    async def embedwatcher_set_non_embed(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("embedwatcher", "non_embed_enabled", enabled, interaction.guild.id, interaction.user.id)
        status = "enabled" if enabled else "disabled"
        await interaction.followup.send(
            f"✅ Non-embed message parsing {status}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.non_embed_enabled` → {enabled} by {interaction.user.mention}.",
            interaction.guild.id
        )
    
    @embedwatcher_group.command(name="reset_non_embed", description="Reset non-embed setting to default")
    @requires_admin()
    async def embedwatcher_reset_non_embed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "non_embed_enabled", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("embedwatcher", "non_embed_enabled", interaction.guild.id)
        status = "ingeschakeld" if default_value else "uitgeschakeld"
        await interaction.followup.send(
            f"✅ Non-embed message parsing reset to default: {status}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.non_embed_enabled` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    
    @embedwatcher_group.command(name="set_process_bot_messages", description="Enable/disable processing of bot's own messages")
    @requires_admin()
    async def embedwatcher_set_process_bot_messages(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("embedwatcher", "process_bot_messages", enabled, interaction.guild.id, interaction.user.id)
        status = "enabled" if enabled else "disabled"
        await interaction.followup.send(
            f"✅ Processing of bot's own messages {status}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.process_bot_messages` → {enabled} by {interaction.user.mention}.",
            interaction.guild.id
        )
    
    @embedwatcher_group.command(name="reset_process_bot_messages", description="Reset process_bot_messages setting to default")
    @requires_admin()
    async def embedwatcher_reset_process_bot_messages(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "process_bot_messages", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("embedwatcher", "process_bot_messages", interaction.guild.id)
        status = "ingeschakeld" if default_value else "uitgeschakeld"
        await interaction.followup.send(
            f"✅ Processing of bot's own messages reset to default: {status}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.process_bot_messages` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "reminder_offset_minutes", interaction.guild.id, interaction.user.id)
        default_minutes = self.settings.get("embedwatcher", "reminder_offset_minutes", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Reminder offset reset to default: {default_minutes} minutes.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="show", description="Show TicketBot settings")
    @requires_admin()
    async def ticketbot_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("ticketbot", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No TicketBot settings registered.", ephemeral=True)
            return
        lines = ["🎟️ **TicketBot settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @ticketbot_group.command(name="set_category", description="Set the ticketcategorie in")
    @requires_admin()
    async def ticketbot_set_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("ticketbot", "category_id", category.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Ticket category set to {category.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` → {category.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_category", description="Reset ticket category to default")
    @requires_admin()
    async def ticketbot_reset_category(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "category_id", interaction.guild.id, interaction.user.id)
        default_category_id = self.settings.get("ticketbot", "category_id", interaction.guild.id)
        formatted = f"<#{default_category_id}>" if default_category_id else "—"
        await interaction.followup.send(
            f"↩️ Ticket category reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="set_staff_role", description="Set the supportrol in")
    @requires_admin()
    async def ticketbot_set_staff_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("ticketbot", "staff_role_id", role.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Support role set to {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` → {role.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_staff_role", description="Reset support role to default")
    @requires_admin()
    async def ticketbot_reset_staff_role(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "staff_role_id", interaction.guild.id, interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "staff_role_id", interaction.guild.id)
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Support role reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="set_escalation_role", description="Set the escalatierol in")
    @requires_admin()
    async def ticketbot_set_escalation_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("ticketbot", "escalation_role_id", role.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Escalation role set to {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` → {role.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_escalation_role", description="Reset escalation role to default")
    @requires_admin()
    async def ticketbot_reset_escalation_role(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "escalation_role_id", interaction.guild.id, interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "escalation_role_id", interaction.guild.id)
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Escalation role reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="show", description="Show Grok / AI settings")
    @requires_admin()
    async def gpt_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("gpt", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No Grok/AI settings registered.", ephemeral=True)
            return
        lines = ["🤖 **Grok / AI settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @gpt_group.command(name="set_model", description="Set the Grok model (bot owner only)")
    @app_commands.describe(
        model="The Grok model to use (e.g. grok-3, grok-4-1-fast-reasoning)",
        guild_id="Target guild ID — use this to set the model for a guild you are not in",
    )
    async def gpt_set_model(self, interaction: discord.Interaction, model: str, guild_id: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id not in config.OWNER_IDS:
            await interaction.followup.send("❌ This command is restricted to bot owners.", ephemeral=True)
            return
        model_clean = model.strip()
        if not model_clean:
            await interaction.followup.send("❌ Model name cannot be empty.", ephemeral=True)
            return
        effective_guild_id, guild_id_error = self._resolve_guild_id(interaction, guild_id)
        if guild_id_error:
            await interaction.followup.send(guild_id_error, ephemeral=True)
            return
        await self.settings.set("gpt", "model", model_clean, effective_guild_id, interaction.user.id)
        guild_label = f"guild `{effective_guild_id}`" if effective_guild_id != interaction.guild_id else "this guild"
        await interaction.followup.send(f"✅ Grok model set to `{model_clean}` for {guild_label}.", ephemeral=True)
        await self._send_audit_log(
            "🤖 Grok",
            f"`gpt.model` → `{model_clean}` for guild `{effective_guild_id}` by {interaction.user.mention}.",
            interaction.guild_id,
        )

    @gpt_group.command(name="reset_model", description="Reset Grok model to default (bot owner only)")
    @app_commands.describe(
        guild_id="Target guild ID — use this to reset the model for a guild you are not in",
    )
    async def gpt_reset_model(self, interaction: discord.Interaction, guild_id: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id not in config.OWNER_IDS:
            await interaction.followup.send("❌ This command is restricted to bot owners.", ephemeral=True)
            return
        effective_guild_id, guild_id_error = self._resolve_guild_id(interaction, guild_id)
        if guild_id_error:
            await interaction.followup.send(guild_id_error, ephemeral=True)
            return
        await self.settings.clear("gpt", "model", effective_guild_id, interaction.user.id)
        default_model = self.settings.get("gpt", "model", effective_guild_id)
        guild_label = f"guild `{effective_guild_id}`" if effective_guild_id != interaction.guild_id else "this guild"
        await interaction.followup.send(
            f"↩️ Grok model reset to default (`{default_model}`) for {guild_label}.", ephemeral=True
        )
        await self._send_audit_log(
            "🤖 Grok",
            f"`gpt.model` reset to default for guild `{effective_guild_id}` by {interaction.user.mention}.",
            interaction.guild_id,
        )
    @gpt_group.command(name="set_temperature", description="Set the Grok temperature")
    @requires_admin()
    async def gpt_set_temperature(
        self,
        interaction: discord.Interaction,
        temperature: app_commands.Range[float, 0.0, 2.0],
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gpt", "temperature", float(temperature), interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Grok temperature set to `{temperature}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 Grok",
            f"`gpt.temperature` → {temperature} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="reset_temperature", description="Reset Grok temperature to default")
    @requires_admin()
    async def gpt_reset_temperature(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gpt", "temperature", interaction.guild.id, interaction.user.id)
        default_temp = self.settings.get("gpt", "temperature", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Grok temperature reset to default: `{default_temp}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 Grok",
            f"`gpt.temperature` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="show", description="Show invite tracker settings")
    @requires_admin()
    async def invites_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("invites", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No invite settings registered.", ephemeral=True)
            return
        lines = ["🎉 **Invite tracker settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @invites_group.command(name="enable", description="Enable/disable de invite tracker in")
    @requires_admin()
    async def invites_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("invites", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ Invite tracker enabled.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → True by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="disable", description="Enable/disable de invite tracker uit")
    @requires_admin()
    async def invites_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("invites", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 Invite tracker disabled.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → False by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="set_channel", description="Set the invite announcement channel")
    @requires_admin()
    async def invites_set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("invites", "announcement_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Invite announcements channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` → {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="reset_channel", description="Reset invite channel to default")
    @requires_admin()
    async def invites_reset_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("invites", "announcement_channel_id", interaction.guild.id, interaction.user.id)
        default_channel = self.settings.get("invites", "announcement_channel_id", interaction.guild.id)
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ Invite channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="set_template", description="Set the invite bericht in")
    @requires_admin()
    @app_commands.choices(
        variant=[
            app_commands.Choice(name="Met inviter", value="with"),
            app_commands.Choice(name="Zonder inviter", value="without"),
        ]
    )
    async def invites_set_template(
        self,
        interaction: discord.Interaction,
        variant: app_commands.Choice[str],
        template: str,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        key = "with_inviter_template" if variant.value == "with" else "no_inviter_template"
        await self.settings.set("invites", key, template, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Invite template voor `{variant.name}` bijgewerkt.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` ingesteld by {interaction.user.mention}.",
            interaction.guild.id
        )
    @invites_group.command(name="reset_template", description="Reset invite template to default")
    @requires_admin()
    @app_commands.choices(
        variant=[
            app_commands.Choice(name="Met inviter", value="with"),
            app_commands.Choice(name="Zonder inviter", value="without"),
        ]
    )
    async def invites_reset_template(
        self,
        interaction: discord.Interaction,
        variant: app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        key = "with_inviter_template" if variant.value == "with" else "no_inviter_template"
        await self.settings.clear("invites", key, interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("invites", key, interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Invite template voor `{variant.name}` reset to default.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @reminders_group.command(name="show", description="Show reminder settings")
    @requires_admin()
    async def reminders_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("reminders", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen reminder settings geregistreerd.", ephemeral=True)
            return
        lines = ["⏰ **Reminder settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @reminders_group.command(name="enable", description="Enable/disable reminders in")
    @requires_admin()
    async def reminders_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ Reminders ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → True by {interaction.user.mention}.",
            interaction.guild.id
        )
    @reminders_group.command(name="disable", description="Enable/disable reminders uit")
    @requires_admin()
    async def reminders_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 Reminders uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → False by {interaction.user.mention}.",
            interaction.guild.id
        )
    @reminders_group.command(name="set_default_channel", description="Set a default reminder channel")
    @requires_admin()
    async def reminders_set_default_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "default_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Default reminder channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` → {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @reminders_group.command(name="reset_default_channel", description="Reset default reminder channel")
    @requires_admin()
    async def reminders_reset_default_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("reminders", "default_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("reminders", "default_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Default channel reset to: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @reminders_group.command(name="set_everyone", description="Sta @everyone mentions toe of niet")
    @requires_admin()
    async def reminders_set_everyone(
        self,
        interaction: discord.Interaction,
        allow: bool,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "allow_everyone_mentions", allow, interaction.guild.id, interaction.user.id)
        status = "allowed" if allow else "uitgeschakeld"
        await interaction.followup.send(
            f"✅ @everyone is nu {status} voor reminders.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.allow_everyone_mentions` → {allow} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @verification_group.command(name="show", description="Show verification settings")
    @requires_admin()
    async def verification_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("verification", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No verification settings registered.", ephemeral=True)
            return
        lines = ["✅ **Verification settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @verification_group.command(name="set_verified_role", description="Set the role given after successful verification")
    @requires_admin()
    async def verification_set_verified_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("verification", "verified_role_id", role.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Verified role set to {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.verified_role_id` → {role.mention} by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="reset_verified_role", description="Reset verified role to default")
    @requires_admin()
    async def verification_reset_verified_role(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("verification", "verified_role_id", interaction.guild.id, interaction.user.id)
        default_role_id = self.settings.get("verification", "verified_role_id", interaction.guild.id)
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Verified role reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.verified_role_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="set_category", description="Set the category for verification channels")
    @requires_admin()
    async def verification_set_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("verification", "category_id", category.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Verification category set to {category.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.category_id` → {category.mention} by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="reset_category", description="Reset verification category to default")
    @requires_admin()
    async def verification_reset_category(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("verification", "category_id", interaction.guild.id, interaction.user.id)
        default_category_id = self.settings.get("verification", "category_id", interaction.guild.id)
        formatted = f"<#{default_category_id}>" if default_category_id else "—"
        await interaction.followup.send(
            f"↩️ Verification category reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.category_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="set_vision_model", description="Set the vision-capable model for verification")
    @requires_admin()
    async def verification_set_vision_model(
        self,
        interaction: discord.Interaction,
        model: str,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        model_clean = model.strip()
        if not model_clean:
            await interaction.followup.send("❌ Model name cannot be empty.", ephemeral=True)
            return

        await self.settings.set("verification", "vision_model", model_clean, interaction.guild.id, interaction.user.id)

        # Warn only for known text-only models (Grok 4.x and newer all support image input)
        text_only_models = {"grok-3", "grok-3-mini", "grok-3-fast", "grok-2", "grok-2-mini"}
        vision_note = (
            "\n⚠️ This model is text-only and does not support image inputs — verification will fail."
        ) if model_clean.lower() in text_only_models else ""

        await interaction.followup.send(
            f"✅ Verification vision model set to `{model_clean}`.{vision_note}",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.vision_model` → `{model_clean}` by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="reset_vision_model", description="Reset vision model to default")
    @requires_admin()
    async def verification_reset_vision_model(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("verification", "vision_model", interaction.guild.id, interaction.user.id)
        default_model = self.settings.get("verification", "vision_model", interaction.guild.id)
        formatted = f"`{default_model}`" if default_model else "—"
        await interaction.followup.send(
            f"↩️ Verification vision model reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.vision_model` reset to default by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(
        name="set_ai_prompt_context",
        description="Set extra context for the AI verifier (e.g. what a valid payment looks like).",
    )
    @requires_admin()
    @app_commands.describe(context="Context text shown to the AI alongside every screenshot (max 1000 chars).")
    async def verification_set_ai_prompt_context(
        self,
        interaction: discord.Interaction,
        context: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        context_clean = context.strip()[:1000]
        if not context_clean:
            await interaction.followup.send("❌ Context cannot be empty.", ephemeral=True)
            return
        await self.settings.set("verification", "ai_prompt_context", context_clean, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ AI prompt context set:\n> {safe_embed_text(context_clean, 200)}",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.ai_prompt_context` updated by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="reset_ai_prompt_context", description="Clear the AI verifier context.")
    @requires_admin()
    async def verification_reset_ai_prompt_context(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("verification", "ai_prompt_context", interaction.guild.id, interaction.user.id)
        await interaction.followup.send("↩️ AI prompt context cleared.", ephemeral=True)
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.ai_prompt_context` cleared by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(
        name="set_reference_image",
        description="Upload a reference payment screenshot the AI uses to judge submissions.",
    )
    @requires_admin()
    @app_commands.describe(image="A clear example of a valid payment confirmation for your community.")
    async def verification_set_reference_image(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()

        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("❌ Please attach an image file (PNG, JPG, etc.).", ephemeral=True)
            return

        # Post the image to the log channel so the URL stays refreshable via fetch_message
        log_channel_id = self.settings_helper.get_int("system", "log_channel_id", interaction.guild.id, fallback=0)
        storage_channel = self.bot.get_channel(log_channel_id) if log_channel_id else interaction.channel
        if not storage_channel or not hasattr(storage_channel, "send"):
            await interaction.followup.send(
                "❌ Could not find a channel to store the reference image. Please configure a log channel first.",
                ephemeral=True,
            )
            return

        import discord as _discord
        storage_text_channel = cast(_discord.TextChannel, storage_channel)

        try:
            file = await image.to_file()
            stored_msg = await storage_text_channel.send(
                content=f"🖼️ **Verification reference image** — uploaded by {interaction.user.mention} for `/config verification`",
                file=file,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Could not store the reference image: {safe_embed_text(str(e), 200)}", ephemeral=True)
            return

        await self.settings.set(
            "verification", "reference_image_channel_id", stored_msg.channel.id,
            interaction.guild.id, interaction.user.id,
        )
        await self.settings.set(
            "verification", "reference_image_message_id", str(stored_msg.id),
            interaction.guild.id, interaction.user.id,
        )

        await interaction.followup.send(
            f"✅ Reference image saved. The AI will now compare every submitted screenshot against this example.\n"
            f"Stored in: {storage_text_channel.mention}",
            ephemeral=True,
        )
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.reference_image` set by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @verification_group.command(name="reset_reference_image", description="Remove the reference payment screenshot.")
    @requires_admin()
    async def verification_reset_reference_image(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()

        channel_id = self.settings_helper.get_int("verification", "reference_image_channel_id", interaction.guild.id, fallback=0)
        message_id_str = self.settings_helper.get_str("verification", "reference_image_message_id", interaction.guild.id, fallback="")

        # Best-effort delete the stored message
        if channel_id and message_id_str:
            try:
                ch = self.bot.get_channel(channel_id)
                if ch and hasattr(ch, "fetch_message"):
                    import discord as _discord
                    text_ch = cast(_discord.TextChannel, ch)
                    msg = await text_ch.fetch_message(int(message_id_str))
                    await msg.delete()
            except Exception:
                pass

        await self.settings.clear("verification", "reference_image_channel_id", interaction.guild.id, interaction.user.id)
        await self.settings.clear("verification", "reference_image_message_id", interaction.guild.id, interaction.user.id)
        await interaction.followup.send("↩️ Reference image removed.", ephemeral=True)
        await self._send_audit_log(
            "✅ Verification",
            f"`verification.reference_image` cleared by {interaction.user.mention}.",
            interaction.guild.id,
        )

    @gdpr_group.command(name="show", description="Show GDPR settings")
    @requires_admin()
    async def gdpr_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("gdpr", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen GDPR settings geregistreerd.", ephemeral=True)
            return
        lines = ["🔒 **GDPR settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @gdpr_group.command(name="enable", description="Enable/disable GDPR functionaliteit in")
    @requires_admin()
    async def gdpr_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gdpr", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ GDPR functionality enabled.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → True by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gdpr_group.command(name="disable", description="Enable/disable GDPR functionaliteit uit")
    @requires_admin()
    async def gdpr_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gdpr", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 GDPR functionality disabled.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → False by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gdpr_group.command(name="set_channel", description="Set the GDPR channel in")
    @requires_admin()
    async def gdpr_set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gdpr", "channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ GDPR channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` → {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gdpr_group.command(name="reset_channel", description="Reset GDPR channel naar standaard")
    @requires_admin()
    async def gdpr_reset_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gdpr", "channel_id", interaction.guild.id, interaction.user.id)
        default_channel = self.settings.get("gdpr", "channel_id", interaction.guild.id)
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ GDPR channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @onboarding_group.command(name="show", description="Show onboarding configuration")
    @requires_admin()
    async def onboarding_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        # Get onboarding settings
        enabled = self.settings.get("onboarding", "enabled", interaction.guild.id)
        mode = self.settings.get("onboarding", "mode", interaction.guild.id)
        completion_role_id = self.settings.get("onboarding", "completion_role_id", interaction.guild.id)
        lines = ["📝 **Onboarding Configuration**"]
        lines.append(f"**Enabled:** {'✅ Yes' if enabled else '❌ No'}")
        lines.append(f"**Mode:** {mode}")
        # Join role (assigned on join, removed on final access role)
        join_role_id = self.settings.get("onboarding", "join_role_id", interaction.guild.id)
        try:
            join_role_id_int = int(join_role_id) if join_role_id else 0
        except (TypeError, ValueError):
            join_role_id_int = 0
        if join_role_id_int:
            join_role = interaction.guild.get_role(join_role_id_int)
            lines.append(f"**Join Role:** {join_role.mention if join_role else f'<@&{join_role_id_int}>'}")
        else:
            lines.append("**Join Role:** Not set")
        if completion_role_id and completion_role_id != 0:
            role = interaction.guild.get_role(completion_role_id)
            lines.append(f"**Completion Role:** {role.mention if role else f'<@&{completion_role_id}>'}")
        else:
            lines.append("**Completion Role:** Not set")
        # Show rules if mode includes rules
        if mode in ["rules_only", "rules_with_questions"]:
            onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
            if onboarding_cog:
                rules = await onboarding_cog.get_guild_rules(interaction.guild.id)
                if rules:
                    lines.append("\n**Rules:**")
                    for i, rule in enumerate(rules, 1):
                        t = rule["title"] if isinstance(rule, dict) else rule[0]
                        d = rule["description"] if isinstance(rule, dict) else rule[1]
                        extra = ""
                        if isinstance(rule, dict):
                            if rule.get("thumbnail_url"):
                                extra += " [thumb]"
                            if rule.get("image_url"):
                                extra += " [img]"
                        lines.append(f"{i}. **{t}** - {d}{extra}")
                else:
                    lines.append("\n⚠️ No rules configured")
            else:
                lines.append("\n❌ Onboarding module not available")
        # Show questions only if mode includes questions
        if mode in ["rules_with_questions", "questions_only"]:
            onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
            if onboarding_cog:
                questions = await onboarding_cog.get_guild_questions(interaction.guild.id)
                if questions:
                    lines.append("\n**Questions:**")
                    for i, q in enumerate(questions, 1):
                        q_type = "Multiple Choice" if q.get("multiple") else ("Text Input" if q.get("type") == "email" else "Single Choice")
                        lines.append(f"{i}. **{q['question']}** ({q_type})")
                else:
                    lines.append("\n⚠️ No questions configured")
            else:
                lines.append("\n❌ Onboarding module not available")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @onboarding_group.command(name="enable", description="Enable onboarding for this server")
    @requires_admin()
    async def onboarding_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("onboarding", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ Onboarding enabled.", ephemeral=True)
        await self._send_audit_log(
            "📝 Onboarding",
            f"Onboarding enabled by {interaction.user.mention}.",
            interaction.guild.id
        )
    @onboarding_group.command(name="disable", description="Disable onboarding for this server")
    @requires_admin()
    async def onboarding_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("onboarding", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 Onboarding disabled.", ephemeral=True)
        await self._send_audit_log(
            "📝 Onboarding",
            f"Onboarding disabled by {interaction.user.mention}.",
            interaction.guild.id
        )
    @onboarding_group.command(name="set_mode", description="Set onboarding mode")
    @app_commands.describe(mode="Choose the onboarding flow type")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Disabled - No onboarding", value="disabled"),
        app_commands.Choice(name="Rules Only - Role when rules accepted (no questions)", value="rules_only"),
        app_commands.Choice(name="Rules + Questions - Role only after all questions completed", value="rules_with_questions"),
        app_commands.Choice(name="Questions Only - Role only after all questions completed", value="questions_only"),
    ])
    @requires_admin()
    async def onboarding_set_mode(self, interaction: discord.Interaction, mode: str) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        valid_modes = ["disabled", "rules_only", "rules_with_questions", "questions_only"]
        if mode not in valid_modes:
            await interaction.followup.send(f"❌ Invalid mode. Choose from: {', '.join(valid_modes)}", ephemeral=True)
            return
        await self.settings.set("onboarding", "mode", mode, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(f"✅ Onboarding mode set to: **{mode}**", ephemeral=True)
        await self._send_audit_log(
            "📝 Onboarding",
            f"Mode set to '{mode}' by {interaction.user.mention}.",
            interaction.guild.id
        )
    @onboarding_group.command(name="set_role", description="Set role to assign after onboarding completion")
    @requires_admin()
    async def onboarding_set_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("onboarding", "completion_role_id", role.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Completion role set to {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "📝 Onboarding",
            f"Completion role set to {role.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @onboarding_group.command(name="reset_role", description="Remove completion role assignment")
    @requires_admin()
    async def onboarding_reset_role(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("onboarding", "completion_role_id", interaction.guild.id, interaction.user.id)
        await interaction.followup.send("↩️ Completion role removed.", ephemeral=True)
        await self._send_audit_log(
            "📝 Onboarding",
            f"Completion role reset by {interaction.user.mention}.",
            interaction.guild.id
        )

    @onboarding_group.command(name="set_join_role", description="Set role to assign immediately when a user joins (temporary join role)")
    @requires_admin()
    async def onboarding_set_join_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("onboarding", "join_role_id", role.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Join role set to {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "📝 Onboarding",
            f"Join role set to {role.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )

    @onboarding_group.command(name="reset_join_role", description="Remove join role assignment on user join")
    @requires_admin()
    async def onboarding_reset_join_role(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("onboarding", "join_role_id", interaction.guild.id, interaction.user.id)
        await interaction.followup.send("↩️ Join role removed.", ephemeral=True)
        await self._send_audit_log(
            "📝 Onboarding",
            f"Join role reset by {interaction.user.mention}.",
            interaction.guild.id
        )

    @onboarding_group.command(name="add_question", description="Add a new onboarding question")
    @requires_admin()
    async def onboarding_add_question(
        self,
        interaction: discord.Interaction,
        step: app_commands.Range[int, 1, 20],
        question: str,
        question_type: str = "select",
        required: bool = True
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        # Validate question type
        valid_types = ["select", "multiselect", "text", "email"]
        if question_type not in valid_types:
            await interaction.followup.send(
                f"❌ Invalid question type. Use: {', '.join(valid_types)}",
                ephemeral=True
            )
            return
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        question_data = {
            "question": question,
            "type": question_type if question_type in ["text", "email"] else None,
            "optional": not required
        }
        if question_type in ["select", "multiselect"]:
            question_data["multiple"] = (question_type == "multiselect")
        success = await onboarding_cog.save_guild_question(interaction.guild.id, step, question_data)
        if success:
            await interaction.followup.send(f"✅ Question added at position {step}.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Question '{question}' added at position {step} by {interaction.user.mention}.",
                interaction.guild.id
        )
        else:
            await interaction.followup.send("❌ Could not save question.", ephemeral=True)
    @onboarding_group.command(name="delete_question", description="Delete an onboarding question")
    @requires_admin()
    async def onboarding_delete_question(
        self,
        interaction: discord.Interaction,
        step: app_commands.Range[int, 1, 20]
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        success = await onboarding_cog.delete_guild_question(interaction.guild.id, step)
        if success:
            await interaction.followup.send(f"✅ Question at position {step} deleted.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Question at position {step} deleted by {interaction.user.mention}.",
                interaction.guild.id
        )
        else:
            await interaction.followup.send("❌ Could not delete question.", ephemeral=True)
    @onboarding_group.command(name="add_rule", description="Add a new onboarding rule")
    @app_commands.describe(
        rule_order="Position (1-20)",
        title="Rule title",
        description="Rule description",
        thumbnail_url="Optional: image URL shown right/top (rechts)",
        image_url="Optional: image URL shown at bottom (onderaan)",
    )
    @requires_admin()
    async def onboarding_add_rule(
        self,
        interaction: discord.Interaction,
        rule_order: app_commands.Range[int, 1, 20],
        title: str,
        description: str,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        success = await onboarding_cog.save_guild_rule(
            interaction.guild.id, rule_order, title, description,
            thumbnail_url=thumbnail_url, image_url=image_url,
        )
        if success:
            await interaction.followup.send(f"✅ Rule added at position {rule_order}.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Rule '{title}' added at position {rule_order} by {interaction.user.mention}.",
                interaction.guild.id
        )
        else:
            await interaction.followup.send("❌ Could not save rule.", ephemeral=True)
    @onboarding_group.command(name="delete_rule", description="Delete an onboarding rule")
    @requires_admin()
    async def onboarding_delete_rule(
        self,
        interaction: discord.Interaction,
        rule_order: app_commands.Range[int, 1, 20]
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        success = await onboarding_cog.delete_guild_rule(interaction.guild.id, rule_order)
        if success:
            await interaction.followup.send(f"✅ Rule at position {rule_order} deleted.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Rule at position {rule_order} deleted by {interaction.user.mention}.",
                interaction.guild.id
        )
        else:
            await interaction.followup.send("❌ Could not delete rule.", ephemeral=True)
    @onboarding_group.command(name="reset_rules", description="Reset to default onboarding rules")
    @requires_admin()
    async def onboarding_reset_rules(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        # Delete all custom rules for this guild
        if onboarding_cog.db:
            async with acquire_safe(onboarding_cog.db) as conn:
                await conn.execute("DELETE FROM guild_rules WHERE guild_id = $1", interaction.guild.id)
            # Clear cache
            if interaction.guild.id in onboarding_cog.guild_rules_cache:
                del onboarding_cog.guild_rules_cache[interaction.guild.id]
            await interaction.followup.send("✅ Onboarding rules reset to default.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Rules reset to default by {interaction.user.mention}.",
                interaction.guild.id
        )
        else:
            await interaction.followup.send("❌ Database not available.", ephemeral=True)
    @onboarding_group.command(name="reset_questions", description="Reset to default onboarding questions")
    @requires_admin()
    async def onboarding_reset_questions(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        # Delete all custom questions for this guild
        if onboarding_cog.db:
            async with acquire_safe(onboarding_cog.db) as conn:
                await conn.execute("DELETE FROM guild_onboarding_questions WHERE guild_id = $1", interaction.guild.id)
            # Clear cache
            if interaction.guild.id in onboarding_cog.guild_questions_cache:
                del onboarding_cog.guild_questions_cache[interaction.guild.id]
            await interaction.followup.send("✅ Onboarding questions reset to default.", ephemeral=True)
            await self._send_audit_log(
                "📝 Onboarding",
                f"Questions reset to default by {interaction.user.mention}.",
                interaction.guild.id
            )
        else:
            await interaction.followup.send("❌ Database not available.", ephemeral=True)

    @onboarding_group.command(name="panel_post", description="Post an onboarding panel with a Start button")
    @requires_admin()
    async def onboarding_panel_post(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        target = channel or cast(discord.TextChannel, interaction.channel)
        if target is None:
            await interaction.response.send_message("❌ No channel specified.", ephemeral=True)
            return

        # Check if onboarding is enabled for this guild
        enabled = self.settings.get("onboarding", "enabled", interaction.guild.id)
        if not enabled:
            await interaction.response.send_message("⚠️ Onboarding is not enabled for this server. Enable it first with `/config onboarding enable`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        embed = EmbedBuilder.success(
            title=f"Welcome to {interaction.guild.name}!",
            description="To get started and learn about our community, click the button below to begin the onboarding process."
        )
        embed.set_footer(text="Complete the onboarding to gain access to the full server!")

        view = StartOnboardingView()
        await target.send(embed=embed, view=view)
        await interaction.followup.send("✅ Onboarding panel posted.", ephemeral=True)

    @onboarding_group.command(name="reorder", description="Reorder onboarding questions by entering question IDs in desired order")
    @requires_admin()
    async def onboarding_reorder(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.response.send_message("❌ Onboarding module not found.", ephemeral=True)
            return
        
        # Fetch all questions for this guild
        questions = await onboarding_cog.get_guild_questions(interaction.guild.id)
        if not questions:
            await interaction.response.send_message("❌ No questions configured for this guild.", ephemeral=True)
            return
        
        # Show modal with current order
        modal = ReorderQuestionsModal(onboarding_cog, interaction.guild.id, questions)
        await interaction.response.send_modal(modal)

    @automod_group.command(name="show", description="Show auto-moderation settings")
    @requires_admin()
    async def automod_show(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("automod", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ No auto-moderation settings registered.", ephemeral=True)
            return
        lines = ["🛡️ **Auto-moderation settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @automod_group.command(name="enable", description="Enable auto-moderation")
    @requires_admin()
    async def automod_enable(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("automod", "enabled", True, guild_id=interaction.guild.id, updated_by=interaction.user.id)
        await interaction.followup.send("✅ Auto-moderation enabled for this server.", ephemeral=True)
        log_guild_action(interaction.guild.id, "Auto-moderation enabled", user=str(interaction.user))

    @automod_group.command(name="disable", description="Disable auto-moderation")
    @requires_admin()
    async def automod_disable(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("automod", "enabled", False, guild_id=interaction.guild.id, updated_by=interaction.user.id)
        await interaction.followup.send("⚠️ Auto-moderation disabled for this server.", ephemeral=True)
        log_guild_action(interaction.guild.id, "Auto-moderation disabled", user=str(interaction.user))

    @automod_group.command(name="set_log_channel", description="Set auto-moderation log channel")
    @requires_admin()
    async def automod_set_log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("automod", "log_channel_id", channel.id, guild_id=interaction.guild.id, updated_by=interaction.user.id)
        await interaction.followup.send(f"✅ Auto-moderation log channel set to {channel.mention}.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation log channel set to {channel.mention}", user=str(interaction.user))

    @automod_group.command(name="reset_log_channel", description="Reset auto-moderation log channel to default")
    @requires_admin()
    async def automod_reset_log_channel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("automod", "log_channel_id", guild_id=interaction.guild.id, updated_by=interaction.user.id)
        await interaction.followup.send("✅ Auto-moderation log channel reset to default.", ephemeral=True)
        log_guild_action(interaction.guild.id, "Auto-moderation log channel reset", user=str(interaction.user))

    @automod_group.command(name="add_spam_rule", description="Add a spam frequency rule")
    @requires_admin()
    async def automod_add_spam_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        max_messages: app_commands.Range[int, 2, 30] = 5,
        time_window_seconds: app_commands.Range[int, 5, 300] = 60,
        action_type: str = "warn",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)
        rule_config = {
            "spam_type": "frequency",
            "max_messages": int(max_messages),
            "time_window": int(time_window_seconds),
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.SPAM.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(
            f"✅ Spam rule created with ID `{rule_id}`.",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation spam rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_badwords_rule", description="Add a bad-words content rule")
    @requires_admin()
    async def automod_add_badwords_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        words: str,
        action_type: str = "delete",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        parsed_words = [w.strip().lower() for w in words.split(",") if w.strip()]
        if not parsed_words:
            await interaction.response.send_message(
                "❌ Please provide at least one word (comma-separated).",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        rule_config = {
            "content_type": "bad_words",
            "words": parsed_words,
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.CONTENT.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(
            f"✅ Bad-words rule created with ID `{rule_id}` ({len(parsed_words)} words).",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation bad-words rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_links_rule", description="Add a link filtering rule")
    @requires_admin()
    async def automod_add_links_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        allow_links: bool = False,
        whitelist: Optional[str] = None,
        blacklist: Optional[str] = None,
        action_type: str = "delete",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)
        whitelist_domains = [d.strip().lower() for d in (whitelist or "").split(",") if d.strip()]
        blacklist_domains = [d.strip().lower() for d in (blacklist or "").split(",") if d.strip()]
        rule_config = {
            "content_type": "links",
            "allow_links": allow_links,
            "whitelist": whitelist_domains,
            "blacklist": blacklist_domains,
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.CONTENT.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(f"✅ Links rule created with ID `{rule_id}`.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation links rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_mentions_rule", description="Add a mention spam rule")
    @requires_admin()
    async def automod_add_mentions_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        max_mentions: app_commands.Range[int, 1, 30] = 5,
        action_type: str = "warn",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)
        rule_config = {
            "content_type": "mentions",
            "max_mentions": int(max_mentions),
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.CONTENT.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(f"✅ Mentions rule created with ID `{rule_id}`.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation mentions rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_caps_rule", description="Add an excessive caps spam rule")
    @requires_admin()
    async def automod_add_caps_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        min_length: app_commands.Range[int, 5, 500] = 10,
        max_caps_ratio: app_commands.Range[float, 0.5, 1.0] = 0.7,
        action_type: str = "warn",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)
        rule_config = {
            "spam_type": "caps",
            "min_length": int(min_length),
            "max_caps_ratio": float(max_caps_ratio),
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.SPAM.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(f"✅ Caps rule created with ID `{rule_id}`.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation caps rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_duplicate_rule", description="Add a duplicate-message spam rule")
    @requires_admin()
    async def automod_add_duplicate_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        max_duplicates: app_commands.Range[int, 2, 10] = 3,
        action_type: str = "warn",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)
        rule_config = {
            "spam_type": "duplicate",
            "max_duplicates": int(max_duplicates),
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.SPAM.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=False,
        )
        await interaction.followup.send(f"✅ Duplicate rule created with ID `{rule_id}`.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation duplicate rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_regex_rule", description="Add a regex content rule (premium)")
    @requires_admin()
    async def automod_add_regex_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        patterns: str,
        action_type: str = "delete",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        has_premium = await guild_has_premium(interaction.guild.id)
        if not has_premium:
            await interaction.response.send_message(
                "❌ Regex rules require an active premium subscription for this guild.",
                ephemeral=True,
            )
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        parsed_patterns = [p.strip() for p in patterns.split(",") if p.strip()]
        if not parsed_patterns:
            await interaction.response.send_message(
                "❌ Please provide at least one regex pattern (comma-separated).",
                ephemeral=True,
            )
            return

        for pattern in parsed_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                await interaction.response.send_message(
                    f"❌ Invalid regex pattern `{pattern}`: {exc}",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True)
        rule_config = {"patterns": parsed_patterns}
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.REGEX.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=True,
        )
        await interaction.followup.send(
            f"✅ Regex rule created with ID `{rule_id}` ({len(parsed_patterns)} patterns).",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation regex rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="add_ai_rule", description="Add an AI-powered content rule (premium)")
    @requires_admin()
    async def automod_add_ai_rule(
        self,
        interaction: discord.Interaction,
        name: str,
        policy: str,
        action_type: str = "delete",
        threshold: app_commands.Range[float, 0.5, 1.0] = 0.7,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        has_premium = await guild_has_premium(interaction.guild.id)
        if not has_premium:
            await interaction.response.send_message(
                "❌ AI moderation rules require an active premium subscription for this guild.",
                ephemeral=True,
            )
            return

        normalized_action = normalize_automod_action_type(action_type)
        if not normalized_action:
            await interaction.response.send_message(
                "❌ Invalid action type. Use: delete, warn, mute, timeout, or ban.",
                ephemeral=True,
            )
            return
        if not await check_advanced_action_premium(interaction, normalized_action):
            return

        await interaction.response.defer(ephemeral=True)

        rule_config = {
            "policy": policy,
            "threshold": threshold,
        }
        action_config: Dict[str, Any] = {}
        if normalized_action == ActionType.MUTE.value:
            action_config = {"duration_minutes": 10}
        if normalized_action == ActionType.TIMEOUT.value:
            action_config = {"duration_minutes": 30}

        rule_id = await self.rule_processor.create_rule(
            guild_id=interaction.guild.id,
            rule_type=RuleType.AI.value,
            name=name,
            config=rule_config,
            action_type=normalized_action,
            action_config=action_config,
            created_by=interaction.user.id,
            is_premium=True,
        )
        await interaction.followup.send(
            f"✅ AI moderation rule created with ID `{rule_id}`.\n"
            f"Policy: {policy}\nThreshold: {threshold}",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation AI rule created: {name}", user=str(interaction.user))

    @automod_group.command(name="rules", description="List all auto-moderation rules")
    @requires_admin()
    async def automod_rules(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        rows = await self.rule_processor.list_rules(interaction.guild.id)
        if not rows:
            await interaction.followup.send("ℹ️ No auto-moderation rules configured yet.", ephemeral=True)
            return

        lines = ["🛡️ **Auto-moderation rules**"]
        for row in rows[:25]:
            status = "✅" if row.get("enabled") else "🚫"
            lines.append(
                f"{status} `#{row.get('id')}` {row.get('name')} — "
                f"type: `{row.get('rule_type')}` | action: `{row.get('action_type')}`"
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @automod_group.command(name="delete_rule", description="Delete an auto-moderation rule by ID")
    @requires_admin()
    async def automod_delete_rule(self, interaction: discord.Interaction, rule_id: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await self.rule_processor.delete_rule(interaction.guild.id, rule_id)
        if not deleted:
            await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Rule `{rule_id}` deleted.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation rule deleted: {rule_id}", user=str(interaction.user))

    @automod_group.command(name="enable_rule", description="Enable an auto-moderation rule by ID")
    @requires_admin()
    async def automod_enable_rule(self, interaction: discord.Interaction, rule_id: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated = await self.rule_processor.update_rule(
            guild_id=interaction.guild.id,
            rule_id=rule_id,
            enabled=True,
        )
        if not updated:
            await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Rule `{rule_id}` enabled.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation rule enabled: {rule_id}", user=str(interaction.user))

    @automod_group.command(name="disable_rule", description="Disable an auto-moderation rule by ID")
    @requires_admin()
    async def automod_disable_rule(self, interaction: discord.Interaction, rule_id: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated = await self.rule_processor.update_rule(
            guild_id=interaction.guild.id,
            rule_id=rule_id,
            enabled=False,
        )
        if not updated:
            await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Rule `{rule_id}` disabled.", ephemeral=True)
        log_guild_action(interaction.guild.id, f"Auto-moderation rule disabled: {rule_id}", user=str(interaction.user))

    @automod_group.command(name="edit_rule", description="Edit an auto-moderation rule")
    @requires_admin()
    async def automod_edit_rule(
        self,
        interaction: discord.Interaction,
        rule_id: int,
        name: Optional[str] = None,
        enabled: Optional[bool] = None,
        action_type: Optional[str] = None,
        max_messages: Optional[app_commands.Range[int, 2, 30]] = None,
        time_window_seconds: Optional[app_commands.Range[int, 5, 300]] = None,
        max_mentions: Optional[app_commands.Range[int, 1, 30]] = None,
        max_duplicates: Optional[app_commands.Range[int, 2, 10]] = None,
        min_length: Optional[app_commands.Range[int, 5, 500]] = None,
        max_caps_ratio: Optional[app_commands.Range[float, 0.5, 1.0]] = None,
        words: Optional[str] = None,
        patterns: Optional[str] = None,
        allow_links: Optional[bool] = None,
        whitelist: Optional[str] = None,
        blacklist: Optional[str] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        if (
            name is None
            and enabled is None
            and action_type is None
            and max_messages is None
            and time_window_seconds is None
            and max_mentions is None
            and max_duplicates is None
            and min_length is None
            and max_caps_ratio is None
            and words is None
            and patterns is None
            and allow_links is None
            and whitelist is None
            and blacklist is None
        ):
            await interaction.response.send_message(
                "❌ Provide at least one field to update.",
                ephemeral=True,
            )
            return

        normalized_action: Optional[str] = None
        if action_type is not None:
            normalized_action = normalize_automod_action_type(action_type)
            if not normalized_action:
                await interaction.response.send_message(
                    "❌ Invalid action_type. Use: delete, warn, mute, timeout, or ban.",
                    ephemeral=True,
                )
                return
            if not await check_advanced_action_premium(interaction, normalized_action):
                return

        await interaction.response.defer(ephemeral=True)
        current_rule = await self.rule_processor.get_rule(interaction.guild.id, rule_id)
        if not current_rule:
            await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
            return

        requested_fields = {
            "max_messages": max_messages is not None,
            "time_window_seconds": time_window_seconds is not None,
            "max_mentions": max_mentions is not None,
            "max_duplicates": max_duplicates is not None,
            "min_length": min_length is not None,
            "max_caps_ratio": max_caps_ratio is not None,
            "words": words is not None,
            "patterns": patterns is not None,
            "allow_links": allow_links is not None,
            "whitelist": whitelist is not None,
            "blacklist": blacklist is not None,
        }
        invalid_msg = validate_rule_update_fields(
            str(current_rule.get("rule_type", "")),
            dict(current_rule.get("config") or {}),
            requested_fields,
        )
        if invalid_msg:
            await interaction.followup.send(invalid_msg, ephemeral=True)
            return

        new_config = dict(current_rule.get("config") or {})
        config_changed = False
        if max_messages is not None:
            new_config["max_messages"] = int(max_messages)
            config_changed = True
        if time_window_seconds is not None:
            new_config["time_window"] = int(time_window_seconds)
            config_changed = True
        if max_mentions is not None:
            new_config["max_mentions"] = int(max_mentions)
            config_changed = True
        if max_duplicates is not None:
            new_config["max_duplicates"] = int(max_duplicates)
            config_changed = True
        if min_length is not None:
            new_config["min_length"] = int(min_length)
            config_changed = True
        if max_caps_ratio is not None:
            new_config["max_caps_ratio"] = float(max_caps_ratio)
            config_changed = True
        if words is not None:
            parsed_words = [w.strip().lower() for w in words.split(",") if w.strip()]
            if not parsed_words:
                await interaction.followup.send("❌ `words` must include at least one comma-separated value.", ephemeral=True)
                return
            new_config["words"] = parsed_words
            config_changed = True
        if patterns is not None:
            parsed_patterns = [p.strip() for p in patterns.split(",") if p.strip()]
            if not parsed_patterns:
                await interaction.followup.send("❌ `patterns` must include at least one comma-separated regex.", ephemeral=True)
                return
            for pattern in parsed_patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    await interaction.followup.send(
                        f"❌ Invalid regex pattern `{pattern}`: {exc}",
                        ephemeral=True,
                    )
                    return
            new_config["patterns"] = parsed_patterns
            config_changed = True
        if allow_links is not None:
            new_config["allow_links"] = allow_links
            config_changed = True
        if whitelist is not None:
            new_config["whitelist"] = [d.strip().lower() for d in whitelist.split(",") if d.strip()]
            config_changed = True
        if blacklist is not None:
            new_config["blacklist"] = [d.strip().lower() for d in blacklist.split(",") if d.strip()]
            config_changed = True

        updated = await self.rule_processor.update_rule(
            guild_id=interaction.guild.id,
            rule_id=rule_id,
            name=name,
            enabled=enabled,
            action_type=normalized_action,
            config=new_config if config_changed else None,
        )
        if not updated:
            await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
            return

        updates: List[str] = []
        if name is not None:
            updates.append(f"name=`{name}`")
        if enabled is not None:
            updates.append(f"enabled=`{enabled}`")
        if normalized_action is not None:
            updates.append(f"action_type=`{normalized_action}`")
        if config_changed:
            updates.append("config=`updated`")
        updates_text = ", ".join(updates) if updates else "updated"

        await interaction.followup.send(
            f"✅ Rule `{rule_id}` updated: {updates_text}.",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation rule updated: {rule_id}", user=str(interaction.user))

    @automod_group.command(name="logs", description="Show recent auto-moderation logs with optional filters")
    @requires_admin()
    async def automod_logs(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
        user_id: Optional[str] = None,
        rule_id: Optional[int] = None,
        action_type: Optional[str] = None,
        days: app_commands.Range[int, 1, 90] = 7,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        from utils.db_helpers import get_bot_db_pool
        pool = get_bot_db_pool(self.bot)
        if not pool:
            await interaction.followup.send("❌ Database temporarily unavailable. Please try again later.", ephemeral=True)
            return

        query_parts = ["SELECT user_id, rule_id, action_taken, timestamp FROM automod_logs WHERE guild_id = $1"]
        params: List[Any] = [interaction.guild.id]
        param_idx = 2

        if user_id:
            try:
                uid = int(user_id)
                query_parts.append(f"AND user_id = ${param_idx}")
                params.append(uid)
                param_idx += 1
            except ValueError:
                await interaction.followup.send("❌ Invalid user_id format.", ephemeral=True)
                return

        if rule_id is not None:
            query_parts.append(f"AND rule_id = ${param_idx}")
            params.append(rule_id)
            param_idx += 1

        if action_type:
            query_parts.append(f"AND action_taken = ${param_idx}")
            params.append(action_type.lower())
            param_idx += 1

        query_parts.append(f"AND timestamp > NOW() - (${param_idx}::text || ' days')::interval")
        params.append(days)
        param_idx += 1

        query_parts.append("ORDER BY timestamp DESC")
        query_parts.append(f"LIMIT ${param_idx}")
        params.append(int(limit))

        query = " ".join(query_parts)

        try:
            async with acquire_safe(pool) as conn:
                rows = await conn.fetch(query, *params)
        except Exception as e:
            logger.error(f"Failed to load automod logs: {e}")
            await interaction.followup.send("❌ Failed to load logs. Please try again.", ephemeral=True)
            return

        if not rows:
            await interaction.followup.send("ℹ️ No auto-moderation logs found matching filters.", ephemeral=True)
            return

        lines = ["📜 **Recent auto-moderation logs**"]
        filter_desc = []
        if user_id:
            filter_desc.append(f"user={user_id}")
        if rule_id is not None:
            filter_desc.append(f"rule={rule_id}")
        if action_type:
            filter_desc.append(f"action={action_type}")
        filter_desc.append(f"last {days}d")
        lines.append(f"_Filters: {', '.join(filter_desc)}_\n")

        for row in rows:
            ts = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if row.get("timestamp") else "unknown-time"
            lines.append(
                f"`{ts}` user=`{row.get('user_id')}` rule=`{row.get('rule_id')}` action=`{row.get('action_taken')}`"
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @automod_group.command(name="set_severity", description="Set rule priority/severity (higher = processed first)")
    @requires_admin()
    async def automod_set_severity(
        self,
        interaction: discord.Interaction,
        rule_id: int,
        severity: app_commands.Range[int, 1, 10],
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        from utils.db_helpers import get_bot_db_pool
        pool = get_bot_db_pool(self.bot)
        if not pool:
            await interaction.followup.send("❌ Database temporarily unavailable. Please try again later.", ephemeral=True)
            return

        try:
            async with acquire_safe(pool) as conn:
                rule_row = await conn.fetchrow(
                    "SELECT id, action_id FROM automod_rules WHERE guild_id = $1 AND id = $2",
                    interaction.guild.id,
                    rule_id,
                )
                if not rule_row:
                    await interaction.followup.send(f"❌ Rule `{rule_id}` not found.", ephemeral=True)
                    return

                await conn.execute(
                    "UPDATE automod_actions SET severity = $1 WHERE id = $2",
                    severity,
                    rule_row["action_id"],
                )
        except Exception as e:
            logger.error(f"Failed to update automod severity: {e}")
            await interaction.followup.send("❌ Failed to update severity. Please try again.", ephemeral=True)
            return

        if hasattr(self, "rule_processor") and self.rule_processor:
            if interaction.guild.id in self.rule_processor._rules_cache:
                del self.rule_processor._rules_cache[interaction.guild.id]

        await interaction.followup.send(
            f"✅ Rule `{rule_id}` severity set to `{severity}` (higher = higher priority).",
            ephemeral=True,
        )
        log_guild_action(interaction.guild.id, f"Auto-moderation rule severity updated: {rule_id} → {severity}", user=str(interaction.user))

    @growth_group.command(name="set_channel", description="Set the channel where shared Growth Check-ins are posted")
    @requires_admin()
    async def growth_set_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        if channel is not None:
            await interaction.response.defer(ephemeral=True)
            await self.settings.set("growth", "log_channel_id", channel.id, interaction.guild.id, interaction.user.id)
            await interaction.followup.send(
                f"✅ Growth Check-in channel set to {channel.mention}.",
                ephemeral=True,
            )
            await self._send_audit_log(
                "⚙️ Setting updated",
                f"`growth.log_channel_id` set to {channel.mention} by {interaction.user.mention}.",
                interaction.guild.id,
            )
        else:
            view = GrowthChannelSetupView(self.settings, interaction.guild, interaction.user)
            await interaction.response.send_message(
                "Pick an existing channel or let me create a dedicated **#growth-checkins** channel:",
                view=view,
                ephemeral=True,
            )

    @growth_group.command(name="reset_channel", description="Remove the Growth Check-in channel configuration")
    @requires_admin()
    async def growth_reset_channel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("growth", "log_channel_id", interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            "↩️ Growth Check-in channel removed. Sharing option will no longer appear.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting reset",
            f"`growth.log_channel_id` cleared by {interaction.user.mention}.",
            interaction.guild.id,
        )

    def _resolve_guild_id(
        self, interaction: discord.Interaction, guild_id_str: Optional[str]
    ) -> Tuple[Optional[int], Optional[str]]:
        """Return (effective_guild_id, error_message). error_message is None on success."""
        if guild_id_str is not None:
            try:
                return int(guild_id_str.strip()), None
            except ValueError:
                return None, f"❌ Invalid guild ID `{guild_id_str}` — must be a numeric snowflake."
        if interaction.guild_id is not None:
            return interaction.guild_id, None
        return None, "❌ No guild context. Provide a `guild_id` when using this command in DMs."

    def _format_value(self, definition: SettingDefinition, value: Any) -> str:
        if value is None:
            return "—"
        if definition.value_type == "channel":
            return f"<#{int(value)}>" if value else "—"
        if definition.value_type == "role":
            return f"<@&{int(value)}>"
        if definition.value_type == "bool":
            return "✅ on" if value else "🚫 off"
        return f"`{value}`"
    async def _send_audit_log(self, title: str, message: str, guild_id: Optional[int] = None) -> None:
        """Send audit log to the correct guild's log channel. Config changes are always logged (critical)."""
        if guild_id is None:
            # Backwards compatibility - skip logging if no guild_id provided
            return
        try:
            channel_id = int(self.settings.get("system", "log_channel_id", guild_id))
        except Exception:
            # No log channel configured for this guild
            log_with_guild(f"No audit log channel configured for configuration changes", guild_id, "debug")
            return
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            log_with_guild(f"Audit log channel {channel_id} not found or not accessible", guild_id, "warning")
            return
        embed = EmbedBuilder.warning(title=title, description=message)
        embed.set_footer(text=f"config | Guild: {guild_id}")
        try:
            # Config changes are always logged (critical level), bypass log level check
            await channel.send(embed=embed)
            log_guild_action(guild_id, "AUDIT_LOG", details=f"config: {title}")
        except Exception as e:
            log_with_guild(f"Could not send audit log: {e}", guild_id, "error")


class GrowthChannelSetupView(discord.ui.View):
    """Shown when /config growth set_channel is called without a channel argument.

    Lets the admin pick an existing channel or create a new #growth-checkins channel.
    """

    def __init__(self, settings, guild: discord.Guild, actor: discord.Member):
        super().__init__(timeout=120)
        self.settings = settings
        self.guild = guild
        self.actor = actor

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Pick an existing channel…",
        min_values=1,
        max_values=1,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        await self.settings.set("growth", "log_channel_id", channel.id, self.guild.id, self.actor.id)
        await interaction.response.edit_message(
            content=f"✅ Growth Check-in channel set to {channel.mention}.",
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Create #growth-checkins", style=discord.ButtonStyle.primary, emoji="🌱")
    async def create_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            channel = await self.guild.create_text_channel(
                "growth-checkins",
                reason=f"Growth Check-in channel created by {self.actor} via /config growth set_channel",
            )
            await self.settings.set("growth", "log_channel_id", channel.id, self.guild.id, self.actor.id)
            await interaction.edit_original_response(
                content=f"✅ Created and configured {channel.mention} as the Growth Check-in channel.",
                view=None,
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="❌ I don't have permission to create channels. Please create one manually and use `/config growth set_channel #channel`.",
                view=None,
            )
        self.stop()


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
