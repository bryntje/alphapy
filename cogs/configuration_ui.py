"""
Setup Wizard UI components for the Configuration cog.

Extracted from configuration.py to keep the main cog file focused on
command registration.  These classes are purely UI (discord.ui.View /
discord.ui.Modal); they hold no slash-command registrations.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal, Optional, Tuple

import discord

from utils.db_helpers import acquire_safe
from utils.embed_builder import EmbedBuilder
from utils.logger import log_with_guild, logger
from utils.timezone import BRUSSELS_TZ


SetupValueType = Literal["channel", "channel_category", "role"]


@dataclass
class SetupStep:
    scope: str
    key: str
    label: str
    value_type: SetupValueType


SETUP_STEPS: List[SetupStep] = [
    SetupStep("system", "log_channel_id", "Do you want to set a log channel for bot messages?", "channel"),
    SetupStep("system", "rules_channel_id", "Set the rules and onboarding channel (#rules)?", "channel"),
    SetupStep("embedwatcher", "announcements_channel_id", "Channel for embed-based reminders?", "channel"),
    SetupStep("invites", "announcement_channel_id", "Channel for invite announcements?", "channel"),
    SetupStep("gdpr", "channel_id", "Channel for GDPR documents?", "channel"),
    SetupStep("ticketbot", "category_id", "Category for new ticket channels?", "channel_category"),
    SetupStep("ticketbot", "staff_role_id", "Staff role for ticket access?", "role"),
]


class SetupWizardView(discord.ui.View):
    """Interactive setup wizard: one step per setting, choose channel/role or skip. All copy in English."""

    def __init__(
        self,
        cog: "Any",  # Configuration — use Any to avoid circular import
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
            from utils.fyi_tips import send_fyi_if_first
            await send_fyi_if_first(self.cog.bot, self.guild_id, "first_config_wizard_complete")
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
    def __init__(self, onboarding_cog: Any, guild_id: int, questions: list):
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
                            embed = EmbedBuilder.warning(
                                title="⚙️ Onboarding questions reordered",
                                description=f"New order: {', '.join(map(str, new_order))}\nBy: {interaction.user.mention}",
                            )
                            await channel.send(embed=embed)
                except Exception:
                    pass

        except Exception as e:
            logger.exception(f"❌ Error reordering questions: {e}")
            await interaction.followup.send(f"❌ Failed to reorder questions: {e}", ephemeral=True)
