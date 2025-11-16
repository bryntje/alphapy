from typing import Any, Optional
import discord
from discord import app_commands
from discord.ext import commands
from utils.checks_interaction import is_owner_or_admin_interaction
from utils.settings_service import SettingsService, SettingDefinition
from utils.logger import log_with_guild, log_guild_action
def requires_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_owner_or_admin_interaction(interaction):
            return True
        raise app_commands.CheckFailure("Je hebt onvoldoende rechten voor dit commando.")
    return app_commands.check(predicate)
class Configuration(commands.Cog):
    config = app_commands.Group(
        name="config",
        description="Beheer bot-instellingen",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )
    system_group = app_commands.Group(
        name="system",
        description="Systeeminstellingen",
        parent=config,
    )
    embedwatcher_group = app_commands.Group(
        name="embedwatcher",
        description="Embed watcher instellingen",
        parent=config,
    )
    ticketbot_group = app_commands.Group(
        name="ticketbot",
        description="TicketBot instellingen",
        parent=config,
    )
    gpt_group = app_commands.Group(
        name="gpt",
        description="GPT instellingen",
        parent=config,
    )
    invites_group = app_commands.Group(
        name="invites",
        description="Invite tracker instellingen",
        parent=config,
    )
    reminders_group = app_commands.Group(
        name="reminders",
        description="Reminder instellingen",
        parent=config,
    )
    gdpr_group = app_commands.Group(
        name="gdpr",
        description="GDPR instellingen",
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
        if not isinstance(settings, SettingsService):
            raise RuntimeError("SettingsService niet beschikbaar op bot instance")
        self.settings: SettingsService = settings
    @config.command(name="scopes", description="Toon alle beschikbare setting scopes")
    @requires_admin()
    async def config_scopes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        scopes = self.settings.scopes()
        if not scopes:
            await interaction.followup.send("⚠️ Geen scopes geregistreerd.", ephemeral=True)
            return
        lines = ["📁 **Beschikbare scopes**:"]
        lines.extend(f"• `{scope}`" for scope in scopes)
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @system_group.command(name="show", description="Toon systeeminstellingen")
    @requires_admin()
    async def system_show(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Deze command werkt alleen in een server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by the check above
        items = self.settings.list_scope("system", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen systeeminstellingen geregistreerd.", ephemeral=True)
            return
        lines = ["🛠️ **System settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @system_group.command(name="set_log_channel", description="Stel het logkanaal in")
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
            f"✅ Logkanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling bijgewerkt",
            f"`system.log_channel_id` ingesteld op {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_log_channel", description="Herstel logkanaal naar standaardwaarde")
    @requires_admin()
    async def system_reset_log_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "log_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "log_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Logkanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling hersteld",
            f"`system.log_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="set_rules_channel", description="Stel het rules kanaal in (#rules)")
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
            f"✅ Rules kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling bijgewerkt",
            f"`system.rules_channel_id` ingesteld op {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_rules_channel", description="Herstel rules kanaal naar standaardwaarde")
    @requires_admin()
    async def system_reset_rules_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "rules_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "rules_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Rules kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling hersteld",
            f"`system.rules_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="set_onboarding_channel", description="Stel het onboarding kanaal in")
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
            f"✅ Onboarding kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling bijgewerkt",
            f"`system.onboarding_channel_id` ingesteld op {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @system_group.command(name="reset_onboarding_channel", description="Herstel onboarding kanaal naar standaardwaarde")
    @requires_admin()
    async def system_reset_onboarding_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("system", "onboarding_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("system", "onboarding_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Onboarding kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling hersteld",
            f"`system.onboarding_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="show", description="Toon embed watcher instellingen")
    @requires_admin()
    async def embedwatcher_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("embedwatcher", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen embed watcher instellingen gevonden.", ephemeral=True)
            return
        lines = ["📣 **Embed watcher settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @embedwatcher_group.command(name="set_announcements", description="Kies het kanaal dat gemonitord wordt")
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
            f"✅ Announcement kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` → {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="reset_announcements", description="Herstel announcement kanaal naar standaard")
    @requires_admin()
    async def embedwatcher_reset_announcements(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "announcements_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("embedwatcher", "announcements_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Announcement kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="set_offset", description="Stel reminder offset in (minuten)")
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
            f"✅ Reminder offset ingesteld op {minutes} minuten.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` → {minutes} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @embedwatcher_group.command(name="reset_offset", description="Herstel reminder offset naar standaard")
    @requires_admin()
    async def embedwatcher_reset_offset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("embedwatcher", "reminder_offset_minutes", interaction.guild.id, interaction.user.id)
        default_minutes = self.settings.get("embedwatcher", "reminder_offset_minutes", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Reminder offset teruggezet naar standaard: {default_minutes} minuten.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="show", description="Toon TicketBot instellingen")
    @requires_admin()
    async def ticketbot_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("ticketbot", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen TicketBot instellingen geregistreerd.", ephemeral=True)
            return
        lines = ["🎟️ **TicketBot settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @ticketbot_group.command(name="set_category", description="Stel de ticketcategorie in")
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
            f"✅ Ticketcategorie ingesteld op {category.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` → {category.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_category", description="Herstel ticketcategorie naar standaard")
    @requires_admin()
    async def ticketbot_reset_category(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "category_id", interaction.guild.id, interaction.user.id)
        default_category_id = self.settings.get("ticketbot", "category_id", interaction.guild.id)
        formatted = f"<#{default_category_id}>" if default_category_id else "—"
        await interaction.followup.send(
            f"↩️ Ticketcategorie teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="set_staff_role", description="Stel de supportrol in")
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
            f"✅ Supportrol ingesteld op {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` → {role.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_staff_role", description="Herstel supportrol naar standaard")
    @requires_admin()
    async def ticketbot_reset_staff_role(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "staff_role_id", interaction.guild.id, interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "staff_role_id", interaction.guild.id)
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Supportrol teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="set_escalation_role", description="Stel de escalatierol in")
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
            f"✅ Escalatierol ingesteld op {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` → {role.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )
    @ticketbot_group.command(name="reset_escalation_role", description="Herstel escalatierol naar standaard")
    @requires_admin()
    async def ticketbot_reset_escalation_role(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("ticketbot", "escalation_role_id", interaction.guild.id, interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "escalation_role_id", interaction.guild.id)
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Escalatierol teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="show", description="Toon GPT instellingen")
    @requires_admin()
    async def gpt_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("gpt", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen GPT instellingen geregistreerd.", ephemeral=True)
            return
        lines = ["🤖 **GPT settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @gpt_group.command(name="set_model", description="Stel het GPT model in")
    @requires_admin()
    async def gpt_set_model(self, interaction: discord.Interaction, model: str):
        await interaction.response.defer(ephemeral=True)
        model_clean = model.strip()
        if not model_clean:
            await interaction.followup.send("❌ Modelnaam mag niet leeg zijn.", ephemeral=True)
            return
        await self.settings.set("gpt", "model", model_clean, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ GPT model ingesteld op `{model_clean}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` → `{model_clean}` door {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="reset_model", description="Herstel GPT model naar standaard")
    @requires_admin()
    async def gpt_reset_model(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gpt", "model", interaction.guild.id, interaction.user.id)
        default_model = self.settings.get("gpt", "model", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ GPT model teruggezet naar standaard: `{default_model}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )
    @gpt_group.command(name="set_temperature", description="Stel de GPT temperatuur in")
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
            f"✅ GPT temperatuur ingesteld op `{temperature}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.temperature` → {temperature} door {interaction.user.mention}.",
            interaction.guild.id
        )    @gpt_group.command(name="reset_temperature", description="Herstel GPT temperatuur naar standaard")
    @requires_admin()
    async def gpt_reset_temperature(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gpt", "temperature", interaction.guild.id, interaction.user.id)
        default_temp = self.settings.get("gpt", "temperature", interaction.guild.id)
        await interaction.followup.send(
            f"↩️ GPT temperatuur teruggezet naar standaard: `{default_temp}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.temperature` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="show", description="Toon invite tracker instellingen")
    @requires_admin()
    async def invites_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("invites", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen invite instellingen geregistreerd.", ephemeral=True)
            return
        lines = ["🎉 **Invite tracker settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @invites_group.command(name="enable", description="Schakel de invite tracker in")
    @requires_admin()
    async def invites_enable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("invites", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ Invite tracker ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → True door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="disable", description="Schakel de invite tracker uit")
    @requires_admin()
    async def invites_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("invites", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 Invite tracker uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → False door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="set_channel", description="Stel het invite announcement kanaal in")
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
            f"✅ Invite announcements kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` → {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="reset_channel", description="Herstel invite kanaal naar standaard")
    @requires_admin()
    async def invites_reset_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("invites", "announcement_channel_id", interaction.guild.id, interaction.user.id)
        default_channel = self.settings.get("invites", "announcement_channel_id", interaction.guild.id)
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ Invite kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="set_template", description="Stel het invite bericht in")
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
        key = "with_inviter_template" if variant.value == "with" else "no_inviter_template"
        await self.settings.set("invites", key, template, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            f"✅ Invite template voor `{variant.name}` bijgewerkt.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` ingesteld door {interaction.user.mention}.",
            interaction.guild.id
        )    @invites_group.command(name="reset_template", description="Herstel invite template naar standaard")
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
        key = "with_inviter_template" if variant.value == "with" else "no_inviter_template"
        await self.settings.clear("invites", key, interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("invites", key, interaction.guild.id)
        await interaction.followup.send(
            f"↩️ Invite template voor `{variant.name}` teruggezet naar standaard.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )    @reminders_group.command(name="show", description="Toon reminder instellingen")
    @requires_admin()
    async def reminders_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("reminders", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen reminder instellingen geregistreerd.", ephemeral=True)
            return
        lines = ["⏰ **Reminder settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @reminders_group.command(name="enable", description="Schakel reminders in")
    @requires_admin()
    async def reminders_enable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ Reminders ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → True door {interaction.user.mention}.",
            interaction.guild.id
        )    @reminders_group.command(name="disable", description="Schakel reminders uit")
    @requires_admin()
    async def reminders_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 Reminders uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → False door {interaction.user.mention}.",
            interaction.guild.id
        )    @reminders_group.command(name="set_default_channel", description="Stel een standaard reminder kanaal in")
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
            f"✅ Standaard reminder kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` → {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )    @reminders_group.command(name="reset_default_channel", description="Herstel standaard reminder kanaal")
    @requires_admin()
    async def reminders_reset_default_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("reminders", "default_channel_id", interaction.guild.id, interaction.user.id)
        default_value = self.settings.get("reminders", "default_channel_id", interaction.guild.id)
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Standaard kanaal teruggezet naar: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )    @reminders_group.command(name="set_everyone", description="Sta @everyone mentions toe of niet")
    @requires_admin()
    async def reminders_set_everyone(
        self,
        interaction: discord.Interaction,
        allow: bool,
    ):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("reminders", "allow_everyone_mentions", allow, interaction.guild.id, interaction.user.id)
        status = "toegestaan" if allow else "uitgeschakeld"
        await interaction.followup.send(
            f"✅ @everyone is nu {status} voor reminders.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.allow_everyone_mentions` → {allow} door {interaction.user.mention}.",
            interaction.guild.id
        )    @gdpr_group.command(name="show", description="Toon GDPR instellingen")
    @requires_admin()
    async def gdpr_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("gdpr", interaction.guild.id)
        if not items:
            await interaction.followup.send("⚠️ Geen GDPR instellingen geregistreerd.", ephemeral=True)
            return
        lines = ["🔒 **GDPR settings**"]
        for definition, value, overridden in items:
            status = "✅ override" if overridden else "🔹 default"
            formatted = self._format_value(definition, value)
            lines.append(f"{status} — `{definition.key}` → {formatted}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @gdpr_group.command(name="enable", description="Schakel GDPR functionaliteit in")
    @requires_admin()
    async def gdpr_enable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gdpr", "enabled", True, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("✅ GDPR functionaliteit ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → True door {interaction.user.mention}.",
            interaction.guild.id
        )    @gdpr_group.command(name="disable", description="Schakel GDPR functionaliteit uit")
    @requires_admin()
    async def gdpr_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.set("gdpr", "enabled", False, interaction.guild.id, interaction.user.id)
        await interaction.followup.send("🛑 GDPR functionaliteit uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → False door {interaction.user.mention}.",
            interaction.guild.id
        )    @gdpr_group.command(name="set_channel", description="Stel het GDPR kanaal in")
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
            f"✅ GDPR kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` → {channel.mention} door {interaction.user.mention}.",
            interaction.guild.id
        )    @gdpr_group.command(name="reset_channel", description="Herstel GDPR kanaal naar standaard")
    @requires_admin()
    async def gdpr_reset_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        assert interaction.guild is not None  # Guaranteed by @requires_admin()
        await self.settings.clear("gdpr", "channel_id", interaction.guild.id, interaction.user.id)
        default_channel = self.settings.get("gdpr", "channel_id", interaction.guild.id)
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ GDPR kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` teruggezet naar standaard door {interaction.user.mention}.",
            interaction.guild.id
        )    @onboarding_group.command(name="show", description="Show onboarding configuration")
    @requires_admin()
    async def onboarding_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
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
                    for i, (title, description) in enumerate(rules, 1):
                        lines.append(f"{i}. **{title}** - {description}")
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
    async def onboarding_enable(self, interaction: discord.Interaction):
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
    async def onboarding_disable(self, interaction: discord.Interaction):
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
    async def onboarding_set_mode(self, interaction: discord.Interaction, mode: str):
        await interaction.response.defer(ephemeral=True)
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
    async def onboarding_reset_role(self, interaction: discord.Interaction):
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
    @requires_admin()
    async def onboarding_add_rule(
        self,
        interaction: discord.Interaction,
        rule_order: app_commands.Range[int, 1, 20],
        title: str,
        description: str
    ):
        await interaction.response.defer(ephemeral=True)
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        success = await onboarding_cog.save_guild_rule(interaction.guild.id, rule_order, title, description)
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
    async def onboarding_reset_rules(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        # Delete all custom rules for this guild
        if onboarding_cog.db:
            async with onboarding_cog.db.acquire() as conn:
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
    async def onboarding_reset_questions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        onboarding_cog = getattr(self.bot, "get_cog", lambda name: None)("Onboarding")
        if not onboarding_cog:
            await interaction.followup.send("❌ Onboarding module not found.", ephemeral=True)
            return
        # Delete all custom questions for this guild
        if onboarding_cog.db:
            async with onboarding_cog.db.acquire() as conn:
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
    def _format_value(self, definition: SettingDefinition, value: Any) -> str:
        if value is None:
            return "—"
        if definition.value_type == "channel":
            return f"<#{int(value)}>" if value else "—"
        if definition.value_type == "role":
            return f"<@&{int(value)}>"
        if definition.value_type == "bool":
            return "✅ aan" if value else "🚫 uit"
        return f"`{value}`"
    async def _send_audit_log(self, title: str, message: str, guild_id: Optional[int] = None) -> None:
        """Send audit log to the correct guild's log channel"""
        if guild_id is None:
            # Backwards compatibility - skip logging if no guild_id provided
            logger.debug("⚠️ _send_audit_log called without guild_id")
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
        embed = discord.Embed(title=title, description=message, color=discord.Color.orange())
        embed.set_footer(text=f"config | Guild: {guild_id}")
        try:
            await channel.send(embed=embed)
            log_guild_action(guild_id, "AUDIT_LOG", details=f"config: {title}")
        except Exception as e:
            log_with_guild(f"Kon audit log niet versturen: {e}", guild_id, "error")
async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
