from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal, Optional, Tuple, cast
import discord
from discord import app_commands
from discord.ext import commands
from utils.validators import validate_admin
from utils.db_helpers import acquire_safe
from utils.embed_builder import EmbedBuilder
from utils.settings_service import SettingsService, SettingDefinition
from utils.logger import log_with_guild, log_guild_action, logger
from utils.timezone import BRUSSELS_TZ
from cogs.reaction_roles import StartOnboardingView

SetupValueType = Literal["channel", "channel_category", "role"]


@dataclass
class SetupStep:
    scope: str
    key: str
    label: str
    value_type: SetupValueType


SETUP_STEPS: List[SetupStep] = [
    SetupStep("system", "log_channel_id", "Do you want to set a log channel for bot messages?", "channel"),
    SetupStep("system", "rules_channel_id", "Set the rules channel (#rules)?", "channel"),
    SetupStep("system", "onboarding_channel_id", "Set the onboarding / welcome channel?", "channel"),
    SetupStep("embedwatcher", "announcements_channel_id", "Channel for embed-based reminders?", "channel"),
    SetupStep("invites", "announcement_channel_id", "Channel for invite announcements?", "channel"),
    SetupStep("gdpr", "channel_id", "Channel for GDPR documents?", "channel"),
    SetupStep("ticketbot", "category_id", "Category for new ticket channels?", "channel_category"),
    SetupStep("ticketbot", "staff_role_id", "Staff role for ticket access?", "role"),
]
def requires_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        is_admin, _ = await validate_admin(interaction, raise_on_fail=False)
        if is_admin:
            return True
        raise app_commands.CheckFailure("Je hebt onvoldoende rechten voor dit commando.")
    return app_commands.check(predicate)
class Configuration(commands.Cog):
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
        description="GPT settings",
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, 'get'):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore
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
    @system_group.command(name="set_rules_channel", description="Set the rules channel (#rules)")
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
    @system_group.command(name="reset_rules_channel", description="Reset rules channel to default value")
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
    @system_group.command(name="set_onboarding_channel", description="Set the onboarding channel")
    @requires_admin()
    async def system_set_onboarding_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("system", "onboarding_channel_id", channel.id, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Onboarding channel set to {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting updated",
            f"`system.onboarding_channel_id` set to {channel.mention} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_onboarding_channel", description="Reset onboarding channel to default value")
    @requires_admin()
    async def system_reset_onboarding_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "onboarding_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "onboarding_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Onboarding channel reset to default: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Setting reset",
            f"`system.onboarding_channel_id` reset to default by {interaction.user.mention}.",
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
    @gpt_group.command(name="show", description="Show GPT settings")
    @requires_admin()
    async def gpt_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        items = self.settings.list_scope("gpt", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen GPT settings geregistreerd.", ephemeral=True)
            return
        lines = ["🤖 **GPT settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @gpt_group.command(name="set_model", description="Set the GPT model in")
    @requires_admin()
    async def gpt_set_model(self, interaction: discord.Interaction, model: str) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        model_clean = model.strip()
        if not model_clean:
            await interaction.followup.send("❌ Model name cannot be empty.", ephemeral=True)
            return
        await self.settings.set("gpt", "model", model_clean, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ GPT model set to `{model_clean}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` → `{model_clean}` by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="reset_model", description="Reset GPT model to default")
    @requires_admin()
    async def gpt_reset_model(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gpt", "model", interaction.guild.id, interaction.user.id)
        default_model = self.settings.get("gpt", "model", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ GPT model reset to default: `{default_model}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` reset to default by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="set_temperature", description="Set the GPT temperature in")
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
            f"✅ GPT temperature set to `{temperature}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.temperature` → {temperature} by {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="reset_temperature", description="Reset GPT temperature to default")
    @requires_admin()
    async def gpt_reset_temperature(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gpt", "temperature", interaction.guild.id, interaction.user.id)
        default_temp = self.settings.get("gpt", "temperature", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ GPT temperature reset to default: `{default_temp}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
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
        app_commands.Choice(name="Rules Only - Show rules and assign role", value="rules_only"),
        app_commands.Choice(name="Rules + Questions - Show rules, ask questions, assign role", value="rules_with_questions"),
        app_commands.Choice(name="Questions Only - Ask questions and assign role", value="questions_only"),
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

        embed = EmbedBuilder.success(
            title=f"Welcome to {interaction.guild.name}!",
            description="To get started and learn about our community, click the button below to begin the onboarding process."
        )
        embed.set_footer(text="Complete the onboarding to gain access to the full server!")

        view = StartOnboardingView()
        await target.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Onboarding panel posted.", ephemeral=True)
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


class SetupWizardView(discord.ui.View):
    """Interactive setup wizard: one step per setting, choose channel/role or skip. All copy in English."""

    def __init__(
        self,
        cog: "Configuration",
        guild_id: int,
        user_id: int,
        steps: List[SetupStep],
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.steps = steps
        self.step_index = 0
        self.configured_in_session: List[Tuple[str, str]] = []  # (question label, chosen value e.g. #channel or @role)

    def _current_step(self) -> Optional[SetupStep]:
        if 0 <= self.step_index < len(self.steps):
            return self.steps[self.step_index]
        return None

    def _build_step_embed(self, step: SetupStep) -> discord.Embed:
        total = len(self.steps)
        current = self.step_index + 1
        embed = discord.Embed(
            title="⚙️ Server setup (step {} of {})".format(current, total),
            description=step.label + "\n\nChoose below or click **Skip**.",
            color=discord.Color.blue(),
            timestamp=datetime.now(BRUSSELS_TZ),
        )
        embed.set_footer(text=f"config start | Step {current}/{total}")
        return embed

    def _build_complete_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="✅ Setup complete",
            description="You can change any setting later with `/config <scope> show` and the set commands.",
            color=discord.Color.green(),
            timestamp=datetime.now(BRUSSELS_TZ),
        )
        if self.configured_in_session:
            lines = [f"**{label}**\n{value}" for label, value in self.configured_in_session]
            value_text = "\n\n".join(lines)
            if len(value_text) > 1024:
                value_text = value_text[:1021] + "…"
            embed.add_field(
                name="Configured in this session",
                value=value_text,
                inline=False,
            )
        embed.set_footer(text="config start | Complete")
        return embed

    def _build_timeout_embed(self) -> discord.Embed:
        return discord.Embed(
            title="⏱️ Setup timed out",
            description="Use `/config start` again to continue.",
            color=discord.Color.orange(),
            timestamp=datetime.now(BRUSSELS_TZ),
        )

    def _clear_and_add_components(self, step: SetupStep) -> None:
        self.clear_items()
        step_id = f"setup_{self.step_index}"
        if step.value_type == "channel":
            channel_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Choose a text channel...",
                min_values=1,
                max_values=1,
                custom_id=f"{step_id}_channel",
            )
            channel_select.callback = self._on_channel_select
            self.add_item(channel_select)
        elif step.value_type == "channel_category":
            category_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.category],
                placeholder="Choose a category...",
                min_values=1,
                max_values=1,
                custom_id=f"{step_id}_category",
            )
            category_select.callback = self._on_channel_select
            self.add_item(category_select)
        else:
            role_select = discord.ui.RoleSelect(
                placeholder="Choose a role...",
                min_values=1,
                max_values=1,
                custom_id=f"{step_id}_role",
            )
            role_select.callback = self._on_role_select
            self.add_item(role_select)
        skip_btn = discord.ui.Button(
            label="Skip",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{step_id}_skip",
        )
        skip_btn.callback = self._on_skip
        self.add_item(skip_btn)

    def _ensure_same_user(self, interaction: discord.Interaction) -> bool:
        """Return False if another user is interacting; sends ephemeral message and returns False."""
        if interaction.user.id != self.user_id:
            return False
        return True

    async def _apply_and_next(
        self,
        interaction: discord.Interaction,
        value: int,
        mention: str,
    ) -> None:
        step = self._current_step()
        if not step:
            await interaction.response.defer(ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.cog.settings.set(step.scope, step.key, value, self.guild_id, self.user_id)
            await self.cog._send_audit_log(
                "⚙️ Setting updated",
                f"`{step.scope}.{step.key}` set to {mention} by <@{self.user_id}> (setup wizard).",
                self.guild_id,
            )
        except Exception as e:
            log_with_guild(f"Setup wizard settings.set failed: {e}", self.guild_id, "error")
            await interaction.followup.send(
                "Failed to save this setting. You can set it later with `/config`.",
                ephemeral=True,
            )
            return
        self.configured_in_session.append((step.label, mention))
        self.step_index += 1
        try:
            await self._render_step(interaction)
        except Exception as e:
            log_with_guild(f"Setup wizard _render_step failed: {e}", self.guild_id, "error")
            await interaction.followup.send(
                "Setup advanced but the message could not be updated. Use `/config start` to continue.",
                ephemeral=True,
            )

    def _get_resolved_channels(self, interaction: discord.Interaction) -> Optional[Any]:
        """Get the first selected channel from a ChannelSelect interaction."""
        data = interaction.data
        if isinstance(data, dict):
            values = data.get("values", [])
            resolved = data.get("resolved", {})
        else:
            values = getattr(data, "values", None) or []
            resolved = getattr(data, "resolved", None) or {}
        if not values or not interaction.guild:
            return None
        try:
            vid = str(values[0])
            cid = int(values[0])
        except (ValueError, TypeError, IndexError):
            return None
        if isinstance(resolved, dict):
            channels = resolved.get("channels", {})
        else:
            channels = getattr(resolved, "channels", None) or {}
        ch = channels.get(vid) or channels.get(str(cid))
        if not ch and interaction.guild:
            ch = interaction.guild.get_channel(cid)
        return ch

    def _get_resolved_role(self, interaction: discord.Interaction) -> Optional[Any]:
        """Get the first selected role from a RoleSelect interaction."""
        data = interaction.data
        if isinstance(data, dict):
            values = data.get("values", [])
            resolved = data.get("resolved", {})
        else:
            values = getattr(data, "values", None) or []
            resolved = getattr(data, "resolved", None) or {}
        if not values or not interaction.guild:
            return None
        try:
            vid = str(values[0])
            rid = int(values[0])
        except (ValueError, TypeError, IndexError):
            return None
        if isinstance(resolved, dict):
            roles = resolved.get("roles", {})
        else:
            roles = getattr(resolved, "roles", None) or {}
        role = roles.get(vid) or (roles.get(str(rid)) if isinstance(roles, dict) else getattr(roles, "get", lambda k: None)(rid))
        if not role and interaction.guild:
            role = interaction.guild.get_role(rid)
        return role

    async def _on_channel_select(self, interaction: discord.Interaction) -> None:
        if not self._ensure_same_user(interaction):
            await interaction.response.send_message(
                "Only the user who started the setup can use this.",
                ephemeral=True,
            )
            return
        channel = self._get_resolved_channels(interaction)
        if not channel:
            await interaction.response.defer(ephemeral=True)
            return
        if isinstance(channel, dict):
            channel_id = int(channel.get("id") or 0)
            mention = f"<#{channel_id}>"
        else:
            channel_id = channel.id
            mention = getattr(channel, "mention", f"<#{channel_id}>")
        await self._apply_and_next(interaction, channel_id, mention)

    async def _on_role_select(self, interaction: discord.Interaction) -> None:
        if not self._ensure_same_user(interaction):
            await interaction.response.send_message(
                "Only the user who started the setup can use this.",
                ephemeral=True,
            )
            return
        role = self._get_resolved_role(interaction)
        if not role:
            await interaction.response.defer(ephemeral=True)
            return
        if isinstance(role, dict):
            role_id = int(role.get("id", 0))
            mention = f"<@&{role_id}>"
        else:
            role_id = role.id
            mention = getattr(role, "mention", f"<@&{role_id}>")
        await self._apply_and_next(interaction, role_id, mention)

    async def _on_skip(self, interaction: discord.Interaction) -> None:
        if not self._ensure_same_user(interaction):
            await interaction.response.send_message(
                "Only the user who started the setup can use this.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        step = self._current_step()
        if step:
            self.configured_in_session.append((step.label, "— Skipped"))
        self.step_index += 1
        try:
            await self._render_step(interaction)
        except Exception as e:
            log_with_guild(f"Setup wizard _render_step failed: {e}", self.guild_id, "error")
            await interaction.followup.send(
                "Could not show the next step. Use `/config start` to continue.",
                ephemeral=True,
            )

    async def _render_step(self, interaction: discord.Interaction) -> None:
        step = self._current_step()
        if step is None:
            log_with_guild(
                f"Setup wizard complete (guild_id={self.guild_id}, configured={len(self.configured_in_session)} steps)",
                self.guild_id,
                "debug",
            )
            embed = self._build_complete_embed()
            self.clear_items()
            self.message = await interaction.edit_original_response(embed=embed, view=self)
            self.stop()
            return
        embed = self._build_step_embed(step)
        self._clear_and_add_components(step)
        self.message = await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        embed = self._build_timeout_embed()
        try:
            await self.message.edit(content=None, embed=embed, view=None)
        except Exception as e:
            log_with_guild(f"Setup wizard timeout message edit failed: {e}", self.guild_id, "debug")


class ReorderQuestionsModal(discord.ui.Modal, title="Reorder Questions"):
    def __init__(self, onboarding_cog, guild_id: int, questions: list):
        super().__init__()
        self.onboarding_cog = onboarding_cog
        self.guild_id = guild_id
        self.questions = questions
        
        # Build description showing current order
        current_order = []
        for i, q in enumerate(questions, 1):
            current_order.append(f"{i}. {q.get('question', 'Question')[:50]}")
        
        # Add text input for new order
        self.order_input = discord.ui.TextInput(
            label="Question Order",
            placeholder=f"Enter question numbers in desired order (e.g., 3,1,2,4)",
            default=", ".join(str(i) for i in range(1, len(questions) + 1)),
            max_length=100,
            required=True
        )
        self.add_item(self.order_input)
        
        # Store question IDs for validation
        # Questions don't have IDs in the default structure, so we'll use step_order
        self.question_ids = list(range(1, len(questions) + 1))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse input (e.g., "3,1,2,4" or "3, 1, 2, 4")
            order_str = self.order_input.value.strip()
            order_parts = [p.strip() for p in order_str.split(",")]
            
            # Validate all are numbers
            try:
                new_order = [int(p) for p in order_parts if p]
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid format. Enter comma-separated numbers (e.g., 3,1,2,4).",
                    ephemeral=True
                )
                return
            
            # Validate all question IDs exist
            if set(new_order) != set(self.question_ids):
                await interaction.followup.send(
                    f"❌ Invalid question numbers. Valid range: 1-{len(self.questions)}.",
                    ephemeral=True
                )
                return
            
            # Validate no duplicates
            if len(new_order) != len(set(new_order)):
                await interaction.followup.send("❌ Duplicate question numbers found.", ephemeral=True)
                return
            
            # Update step_order in database
            if not self.onboarding_cog.db:
                await interaction.followup.send("❌ Database not available.", ephemeral=True)
                return
            
            async with acquire_safe(self.onboarding_cog.db) as conn:
                async with conn.transaction():
                    # Update each question's step_order
                    for new_position, question_num in enumerate(new_order, 1):
                        # Find the question at the old position (question_num)
                        # We need to get the actual question from the database to update it
                        # Since questions are indexed by step_order, we need to update carefully
                        await conn.execute(
                            """
                            UPDATE guild_onboarding_questions
                            SET step_order = $1 + 1000  -- Temporary value to avoid conflicts
                            WHERE guild_id = $2 AND step_order = $3
                            """,
                            new_position + 1000, self.guild_id, question_num
                        )
                    
                    # Now set final step_order values
                    for new_position, question_num in enumerate(new_order, 1):
                        await conn.execute(
                            """
                            UPDATE guild_onboarding_questions
                            SET step_order = $1
                            WHERE guild_id = $2 AND step_order = $3 + 1000
                            """,
                            new_position, self.guild_id, question_num + 1000
                        )
            
            # Clear cache
            if self.guild_id in self.onboarding_cog.guild_questions_cache:
                del self.onboarding_cog.guild_questions_cache[self.guild_id]
            
            await interaction.followup.send(
                f"✅ Questions reordered successfully. New order: {', '.join(map(str, new_order))}",
                ephemeral=True
            )
            
            # Log the change
            settings = getattr(interaction.client, "settings", None)
            if settings:
                try:
                    channel_id = int(settings.get("system", "log_channel_id", self.guild_id))
                    if channel_id:
                        channel = interaction.client.get_channel(channel_id)
                        if isinstance(channel, (discord.TextChannel, discord.Thread)):
                            await channel.send(
                                embed=EmbedBuilder.warning(
                                    title="⚙️ Onboarding questions reordered",
                                    description=f"New order: {', '.join(map(str, new_order))}\nBy: {interaction.user.mention}"
                                )
                            )
                except Exception:
                    pass
        
        except Exception as e:
            logger.exception(f"❌ Error reordering questions: {e}")
            await interaction.followup.send(f"❌ Failed to reorder questions: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
