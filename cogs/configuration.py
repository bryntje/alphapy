from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks_interaction import is_owner_or_admin_interaction
from utils.settings_service import SettingsService, SettingDefinition


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
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("system")
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
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("system", "log_channel_id", channel.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Logkanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling bijgewerkt",
            f"`system.log_channel_id` ingesteld op {channel.mention} door {interaction.user.mention}.",
        )

    @system_group.command(name="reset_log_channel", description="Herstel logkanaal naar standaardwaarde")
    @requires_admin()
    async def system_reset_log_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("system", "log_channel_id", updated_by=interaction.user.id)
        default_value = self.settings.get("system", "log_channel_id")
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Logkanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⚙️ Instelling hersteld",
            f"`system.log_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @embedwatcher_group.command(name="show", description="Toon embed watcher instellingen")
    @requires_admin()
    async def embedwatcher_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("embedwatcher")
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
        await self.settings.set("embedwatcher", "announcements_channel_id", channel.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Announcement kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` → {channel.mention} door {interaction.user.mention}.",
        )

    @embedwatcher_group.command(name="reset_announcements", description="Herstel announcement kanaal naar standaard")
    @requires_admin()
    async def embedwatcher_reset_announcements(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("embedwatcher", "announcements_channel_id", updated_by=interaction.user.id)
        default_value = self.settings.get("embedwatcher", "announcements_channel_id")
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Announcement kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔔 Embed watcher",
            f"`embedwatcher.announcements_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @embedwatcher_group.command(name="set_offset", description="Stel reminder offset in (minuten)")
    @requires_admin()
    async def embedwatcher_set_offset(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 0, 4320],
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("embedwatcher", "reminder_offset_minutes", minutes, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Reminder offset ingesteld op {minutes} minuten.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` → {minutes} door {interaction.user.mention}.",
        )

    @embedwatcher_group.command(name="reset_offset", description="Herstel reminder offset naar standaard")
    @requires_admin()
    async def embedwatcher_reset_offset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("embedwatcher", "reminder_offset_minutes", updated_by=interaction.user.id)
        default_minutes = self.settings.get("embedwatcher", "reminder_offset_minutes")
        await interaction.followup.send(
            f"↩️ Reminder offset teruggezet naar standaard: {default_minutes} minuten.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔁 Reminder offset",
            f"`embedwatcher.reminder_offset_minutes` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="show", description="Toon TicketBot instellingen")
    @requires_admin()
    async def ticketbot_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("ticketbot")
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
        await self.settings.set("ticketbot", "category_id", category.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Ticketcategorie ingesteld op {category.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` → {category.mention} door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="reset_category", description="Herstel ticketcategorie naar standaard")
    @requires_admin()
    async def ticketbot_reset_category(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("ticketbot", "category_id", updated_by=interaction.user.id)
        default_category_id = self.settings.get("ticketbot", "category_id")
        formatted = f"<#{default_category_id}>" if default_category_id else "—"
        await interaction.followup.send(
            f"↩️ Ticketcategorie teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.category_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="set_staff_role", description="Stel de supportrol in")
    @requires_admin()
    async def ticketbot_set_staff_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("ticketbot", "staff_role_id", role.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Supportrol ingesteld op {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` → {role.mention} door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="reset_staff_role", description="Herstel supportrol naar standaard")
    @requires_admin()
    async def ticketbot_reset_staff_role(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("ticketbot", "staff_role_id", updated_by=interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "staff_role_id")
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Supportrol teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.staff_role_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="set_escalation_role", description="Stel de escalatierol in")
    @requires_admin()
    async def ticketbot_set_escalation_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("ticketbot", "escalation_role_id", role.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Escalatierol ingesteld op {role.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` → {role.mention} door {interaction.user.mention}.",
        )

    @ticketbot_group.command(name="reset_escalation_role", description="Herstel escalatierol naar standaard")
    @requires_admin()
    async def ticketbot_reset_escalation_role(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("ticketbot", "escalation_role_id", updated_by=interaction.user.id)
        default_role_id = self.settings.get("ticketbot", "escalation_role_id")
        formatted = f"<@&{default_role_id}>" if default_role_id else "—"
        await interaction.followup.send(
            f"↩️ Escalatierol teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎟️ TicketBot",
            f"`ticketbot.escalation_role_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @gpt_group.command(name="show", description="Toon GPT instellingen")
    @requires_admin()
    async def gpt_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("gpt")
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
        await self.settings.set("gpt", "model", model_clean, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ GPT model ingesteld op `{model_clean}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` → `{model_clean}` door {interaction.user.mention}.",
        )

    @gpt_group.command(name="reset_model", description="Herstel GPT model naar standaard")
    @requires_admin()
    async def gpt_reset_model(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("gpt", "model", updated_by=interaction.user.id)
        default_model = self.settings.get("gpt", "model")
        await interaction.followup.send(
            f"↩️ GPT model teruggezet naar standaard: `{default_model}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.model` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @gpt_group.command(name="set_temperature", description="Stel de GPT temperatuur in")
    @requires_admin()
    async def gpt_set_temperature(
        self,
        interaction: discord.Interaction,
        temperature: app_commands.Range[float, 0.0, 2.0],
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("gpt", "temperature", float(temperature), updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ GPT temperatuur ingesteld op `{temperature}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.temperature` → {temperature} door {interaction.user.mention}.",
        )

    @gpt_group.command(name="reset_temperature", description="Herstel GPT temperatuur naar standaard")
    @requires_admin()
    async def gpt_reset_temperature(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("gpt", "temperature", updated_by=interaction.user.id)
        default_temp = self.settings.get("gpt", "temperature")
        await interaction.followup.send(
            f"↩️ GPT temperatuur teruggezet naar standaard: `{default_temp}`.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🤖 GPT",
            f"`gpt.temperature` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @invites_group.command(name="show", description="Toon invite tracker instellingen")
    @requires_admin()
    async def invites_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("invites")
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
        await self.settings.set("invites", "enabled", True, updated_by=interaction.user.id)
        await interaction.followup.send("✅ Invite tracker ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → True door {interaction.user.mention}.",
        )

    @invites_group.command(name="disable", description="Schakel de invite tracker uit")
    @requires_admin()
    async def invites_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("invites", "enabled", False, updated_by=interaction.user.id)
        await interaction.followup.send("🛑 Invite tracker uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.enabled` → False door {interaction.user.mention}.",
        )

    @invites_group.command(name="set_channel", description="Stel het invite announcement kanaal in")
    @requires_admin()
    async def invites_set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("invites", "announcement_channel_id", channel.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Invite announcements kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` → {channel.mention} door {interaction.user.mention}.",
        )

    @invites_group.command(name="reset_channel", description="Herstel invite kanaal naar standaard")
    @requires_admin()
    async def invites_reset_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("invites", "announcement_channel_id", updated_by=interaction.user.id)
        default_channel = self.settings.get("invites", "announcement_channel_id")
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ Invite kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.announcement_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @invites_group.command(name="set_template", description="Stel het invite bericht in")
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
        await self.settings.set("invites", key, template, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Invite template voor `{variant.name}` bijgewerkt.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` ingesteld door {interaction.user.mention}.",
        )

    @invites_group.command(name="reset_template", description="Herstel invite template naar standaard")
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
        await self.settings.clear("invites", key, updated_by=interaction.user.id)
        default_value = self.settings.get("invites", key)
        await interaction.followup.send(
            f"↩️ Invite template voor `{variant.name}` teruggezet naar standaard.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🎉 Invites",
            f"`invites.{key}` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @reminders_group.command(name="show", description="Toon reminder instellingen")
    @requires_admin()
    async def reminders_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("reminders")
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
        await self.settings.set("reminders", "enabled", True, updated_by=interaction.user.id)
        await interaction.followup.send("✅ Reminders ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → True door {interaction.user.mention}.",
        )

    @reminders_group.command(name="disable", description="Schakel reminders uit")
    @requires_admin()
    async def reminders_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("reminders", "enabled", False, updated_by=interaction.user.id)
        await interaction.followup.send("🛑 Reminders uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.enabled` → False door {interaction.user.mention}.",
        )

    @reminders_group.command(name="set_default_channel", description="Stel een standaard reminder kanaal in")
    @requires_admin()
    async def reminders_set_default_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("reminders", "default_channel_id", channel.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ Standaard reminder kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` → {channel.mention} door {interaction.user.mention}.",
        )

    @reminders_group.command(name="reset_default_channel", description="Herstel standaard reminder kanaal")
    @requires_admin()
    async def reminders_reset_default_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("reminders", "default_channel_id", updated_by=interaction.user.id)
        default_value = self.settings.get("reminders", "default_channel_id")
        formatted = f"<#{default_value}>" if default_value else "—"
        await interaction.followup.send(
            f"↩️ Standaard kanaal teruggezet naar: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.default_channel_id` teruggezet naar standaard door {interaction.user.mention}.",
        )

    @reminders_group.command(name="set_everyone", description="Sta @everyone mentions toe of niet")
    @requires_admin()
    async def reminders_set_everyone(
        self,
        interaction: discord.Interaction,
        allow: bool,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("reminders", "allow_everyone_mentions", allow, updated_by=interaction.user.id)
        status = "toegestaan" if allow else "uitgeschakeld"
        await interaction.followup.send(
            f"✅ @everyone is nu {status} voor reminders.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "⏰ Reminders",
            f"`reminders.allow_everyone_mentions` → {allow} door {interaction.user.mention}.",
        )

    @gdpr_group.command(name="show", description="Toon GDPR instellingen")
    @requires_admin()
    async def gdpr_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = self.settings.list_scope("gdpr")
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
        await self.settings.set("gdpr", "enabled", True, updated_by=interaction.user.id)
        await interaction.followup.send("✅ GDPR functionaliteit ingeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → True door {interaction.user.mention}.",
        )

    @gdpr_group.command(name="disable", description="Schakel GDPR functionaliteit uit")
    @requires_admin()
    async def gdpr_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("gdpr", "enabled", False, updated_by=interaction.user.id)
        await interaction.followup.send("🛑 GDPR functionaliteit uitgeschakeld.", ephemeral=True)
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.enabled` → False door {interaction.user.mention}.",
        )

    @gdpr_group.command(name="set_channel", description="Stel het GDPR kanaal in")
    @requires_admin()
    async def gdpr_set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.settings.set("gdpr", "channel_id", channel.id, updated_by=interaction.user.id)
        await interaction.followup.send(
            f"✅ GDPR kanaal ingesteld op {channel.mention}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` → {channel.mention} door {interaction.user.mention}.",
        )

    @gdpr_group.command(name="reset_channel", description="Herstel GDPR kanaal naar standaard")
    @requires_admin()
    async def gdpr_reset_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.settings.clear("gdpr", "channel_id", updated_by=interaction.user.id)
        default_channel = self.settings.get("gdpr", "channel_id")
        formatted = f"<#{default_channel}>" if default_channel else "—"
        await interaction.followup.send(
            f"↩️ GDPR kanaal teruggezet naar standaard: {formatted}.",
            ephemeral=True,
        )
        await self._send_audit_log(
            "🔒 GDPR",
            f"`gdpr.channel_id` teruggezet naar standaard door {interaction.user.mention}.",
        )


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

    async def _send_audit_log(self, title: str, message: str) -> None:
        try:
            channel_id = int(self.settings.get("system", "log_channel_id"))
        except Exception:
            return

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        embed = discord.Embed(title=title, description=message, color=discord.Color.orange())
        embed.set_footer(text="config")
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuration(bot))
