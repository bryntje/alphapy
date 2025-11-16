import discord
from discord.ext import commands
import json
import logging
import uuid
import re
import asyncio
from typing import Optional, Dict, Any, cast
from config import ROLE_ID, LOG_CHANNEL_ID
import asyncpg
from asyncpg import exceptions as pg_exceptions
import config

# Configureer de logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

class Onboarding(commands.Cog):
    """Cog that manages the onboarding process for new users."""
    
    def __init__(self, bot):
        self.bot = bot
        # Track current step and answers per user.
        self.active_sessions = {}  # { user_id: {"step": int, "answers": {}} }
        # Regex for email validation
        self.EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")

        # Default questions (used when no custom questions are configured for a guild)
        self.default_questions = [
            {
                "question": "📣 How did you find our community?",
                "options": [
                    ("Invited by a member", "friend"),
                    ("Social Media", "social"),
                    ("Online Search", "search"),
                    ("Other", "other")
                ],
                "followup": {
                    "friend": {"question": "Who invited you?"},
                    "social": {"question": "Which platform?"},
                    "search": {"question": "What did you search for?"},
                    "other": {"question": "How did you find us?"}
                }
            },
            {
                "question": "🎯 What brings you to our community?",
                "options": [
                    ("Learn new skills", "learning"),
                    ("Network with like-minded people", "networking"),
                    ("Share knowledge & experience", "sharing"),
                    ("Find opportunities", "opportunities"),
                    ("Other", "other")
                ],
                "multiple": True
            },
            {
                "question": "💬 How would you like to connect with the community?",
                "options": [
                    ("Join discussions in channels", "discussions"),
                    ("Attend community events", "events"),
                    ("One-on-one conversations", "personal"),
                    ("Just observe for now", "observe")
                ],
                "multiple": True
            },
            {
                "question": "📧 What's your email address? (Optional)",
                "type": "email",
                "optional": True
            }
        ]

        # Cache for guild questions (guild_id -> questions list)
        self.guild_questions_cache = {}

        self.db: Optional[asyncpg.Pool] = None

    async def get_guild_questions(self, guild_id: int) -> list:
        """Load questions for a specific guild from database, or use defaults if none configured."""
        # Check cache first
        if guild_id in self.guild_questions_cache:
            return self.guild_questions_cache[guild_id]

        if not await self._ensure_pool():
            logger.warning(f"Database not available, using default questions for guild {guild_id}")
            return self.default_questions

        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT question, question_type, options, followup, required
                    FROM guild_onboarding_questions
                    WHERE guild_id = $1 AND enabled = TRUE
                    ORDER BY step_order
                """, guild_id)

                if rows:
                    questions = []
                    for row in rows:
                        question_data = {
                            "question": row["question"],
                            "type": row["question_type"] if row["question_type"] in ["email", "text"] else None,
                            "optional": not row["required"]
                        }

                        if row["question_type"] in ["select", "multiselect"]:
                            if row["options"]:
                                # Convert JSONB options to tuple format expected by the code
                                question_data["options"] = [
                                    (opt["label"], opt["value"]) for opt in row["options"]
                                ]
                            if row["question_type"] == "multiselect":
                                question_data["multiple"] = True
                            if row["followup"]:
                                question_data["followup"] = row["followup"]

                        questions.append(question_data)

                    self.guild_questions_cache[guild_id] = questions
                    return questions
                else:
                    # No custom questions configured, use defaults
                    self.guild_questions_cache[guild_id] = self.default_questions
                    return self.default_questions

        except Exception as e:
            logger.error(f"Failed to load questions for guild {guild_id}: {e}")
            return self.default_questions

    async def save_guild_question(self, guild_id: int, step_order: int, question_data: dict) -> bool:
        """Save a question for a specific guild."""
        if not await self._ensure_pool():
            return False

        try:
            async with self.db.acquire() as conn:
                # Convert options from tuple format to JSONB
                options_json = None
                if "options" in question_data and question_data["options"]:
                    options_json = [
                        {"label": label, "value": value}
                        for label, value in question_data["options"]
                    ]

                followup_json = question_data.get("followup")

                await conn.execute("""
                    INSERT INTO guild_onboarding_questions
                    (guild_id, step_order, question, question_type, options, followup, required, enabled)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
                    ON CONFLICT (guild_id, step_order)
                    DO UPDATE SET
                        question = EXCLUDED.question,
                        question_type = EXCLUDED.question_type,
                        options = EXCLUDED.options,
                        followup = EXCLUDED.followup,
                        required = EXCLUDED.required,
                        updated_at = CURRENT_TIMESTAMP
                """,
                guild_id,
                step_order,
                question_data["question"],
                question_data.get("type", "select") if question_data.get("type") else
                ("multiselect" if question_data.get("multiple") else "select"),
                options_json,
                followup_json,
                not question_data.get("optional", False)
                )

                # Clear cache for this guild
                if guild_id in self.guild_questions_cache:
                    del self.guild_questions_cache[guild_id]

                return True

        except Exception as e:
            logger.error(f"Failed to save question for guild {guild_id}: {e}")
            return False

    async def delete_guild_question(self, guild_id: int, step_order: int) -> bool:
        """Delete a question for a specific guild."""
        if not await self._ensure_pool():
            return False

        try:
            async with self.db.acquire() as conn:
                await conn.execute("""
                    DELETE FROM guild_onboarding_questions
                    WHERE guild_id = $1 AND step_order = $2
                """, guild_id, step_order)

                # Clear cache for this guild
                if guild_id in self.guild_questions_cache:
                    del self.guild_questions_cache[guild_id]

                return True

        except Exception as e:
            logger.error(f"Failed to delete question for guild {guild_id}: {e}")
            return False
        
    def _value_to_label(self, q_data: dict, value: object) -> str:
        options = q_data.get("options")
        if not isinstance(options, list):
            return str(value)
        for label, val in options:
            if val == value:
                return label
        return str(value)

    def _format_answer(self, q_data: dict, raw_answer: object) -> str:
        if isinstance(raw_answer, dict):
            choice_value = raw_answer.get("choice")
            choice_label = self._value_to_label(q_data, choice_value)
            followup_text = raw_answer.get("followup")
            followup_label = raw_answer.get("followup_label") or "Details"
            return f"{choice_label} — {followup_label}: {followup_text}" if followup_text else f"{choice_label}"
        if isinstance(raw_answer, list):
            mapped = [self._value_to_label(q_data, v) for v in raw_answer]
            return ", ".join(mapped) if mapped else "No response"
        return self._value_to_label(q_data, raw_answer)

    async def setup_database(self):
        """Initialiseer de PostgreSQL database en maak tabellen aan indien nodig."""
        await self._ensure_pool()

    async def _connect_pool(self) -> None:
        pool = await asyncpg.create_pool(config.DATABASE_URL)
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS onboarding (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    responses JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(guild_id, user_id)
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_onboarding_questions (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    step_order INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'select', -- 'select', 'multiselect', 'text', 'email'
                    options JSONB, -- For select/multiselect: [{"label": "Option 1", "value": "value1"}, ...]
                    followup JSONB, -- For conditional followups: {"value": {"question": "Followup question"}}
                    required BOOLEAN DEFAULT TRUE,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, step_order)
                );
            ''')
        self.db = pool
        logger.info("✅ Onboarding: DB pool ready")

    async def _ensure_pool(self, *, attempts: int = 3, base_delay: float = 2.0) -> bool:
        if self.db is not None:
            return True

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                await self._connect_pool()
                return True
            except (pg_exceptions.PostgresError, ConnectionError, OSError) as exc:
                last_error = exc
                logger.warning(
                    f"⚠️ Onboarding: DB connect failed (attempt {attempt}/{attempts}): {exc}"
                )
                await asyncio.sleep(base_delay * attempt)
            except Exception as exc:
                last_error = exc
                logger.exception("❌ Onboarding: onverwachte DB-init fout")
                break

        logger.error(f"❌ Onboarding: kon DB-verbinding niet opzetten: {last_error}")
        return False

    async def send_next_question(self, interaction: discord.Interaction, step: int = 0, answers: Optional[dict] = None):
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else 0

        # Ensure there's an active session for this user
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {"step": 0, "answers": {}}
        session = self.active_sessions[user_id]

        # Use existing answers or update the session
        if answers is None:
            answers = session["answers"]
        else:
            session["answers"] = answers

        # Get questions for this guild
        questions = await self.get_guild_questions(guild_id)

        # If all questions are answered, process completion
        if step >= len(questions):
            logger.info(f"🎉 Onboarding completed for {interaction.user.display_name}!")

            summary_embed = discord.Embed(
                title="📜 Onboarding Summary",
                description=f"Here is a summary of your onboarding responses, {interaction.user.display_name}:",
                color=discord.Color.blue()
            )
            for idx, question in enumerate(questions):
                raw_answer = (answers or {}).get(idx, "No response")
                answer_text = self._format_answer(question, raw_answer)
                summary_embed.add_field(name=f"**{question['question']}**", value=f"➜ {answer_text}", inline=False)

            # Verstuur de samenvatting als ephemeral bericht naar de gebruiker
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=summary_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=summary_embed, ephemeral=True)

            # Save the onboarding data to the database
            stored = await self.store_onboarding_data(interaction.guild.id, user_id, answers)
            if not stored:
                await interaction.followup.send(
                    "⚠️ Onboarding data could not be saved. Please try again later or contact an admin.",
                    ephemeral=True
                )

            # Build and send a log embed to the log channel
            log_embed = discord.Embed(
                title="📝 Onboarding Log",
                description=f"**User:** {interaction.user} ({interaction.user.id})",
                color=discord.Color.green()
            )
            for idx, question in enumerate(questions):
                raw_answer = (answers or {}).get(idx, "No response")
                answer_text = self._format_answer(question, raw_answer)
                log_embed.add_field(name=question['question'], value=f"➜ {answer_text}", inline=False)

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=log_embed)

            # Automatische roltoewijzing
            try:
                guild = interaction.guild
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        role = guild.get_role(ROLE_ID)
                        if role:
                            await member.add_roles(role)
                            logger.info(f"Assigned role {role.name} to {member.display_name}")
            except Exception as e:
                logger.error(f"Error assigning role to user {user_id}: {e}")

            return

        # Get the current question
        q_data = questions[step]

        # If this question requires free text input, send a modal
        if q_data.get("input"):
            modal = TextInputModal(title=q_data["question"], step=step, answers=answers or {}, onboarding=self)
            await interaction.response.send_modal(modal)
            return

        # Anders, bouw een embed en view voor de vraag met opties
        embed = discord.Embed(title="📝 Onboarding Form", description=q_data["question"], color=discord.Color.blue())
        view = OnboardingView(step=step, answers=answers or {}, onboarding=self)

        if q_data.get("multiple"):
            # Multi-select: toon enkel de select; geen confirm-knop nodig
            view.add_item(OnboardingSelect(step=step, options=q_data["options"], onboarding=self, view_id=view.view_id))
        else:
            # Voeg knoppen toe voor single-select vragen
            for label, value in q_data["options"]:
                view.add_item(OnboardingButton(label=label, value=value, step=step, onboarding=self))

        # Alleen confirm-knop voor single-select vragen
        if not q_data.get("multiple"):
            confirm_button = ConfirmButton(step, answers or {}, self)
            confirm_button.disabled = True
            view.add_item(confirm_button)

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def store_onboarding_data(self, guild_id: int, user_id, responses) -> bool:
        """Saves onboarding data to the database."""
        if not await self._ensure_pool():
            logger.error("❌ Onboarding: database not available, data not saved")
            return False

        assert self.db is not None
        try:
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO onboarding (guild_id, user_id, responses)
                    VALUES ($1, $2, $3)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET responses = $3;
                    """,
                    guild_id, user_id, json.dumps(responses)
                )
            logger.info(f"✅ Onboarding data opgeslagen voor {user_id}")
            return True
        except Exception as exc:
            logger.exception(f"❌ Onboarding: opslaan mislukt voor {user_id}: {exc}")
            return False

class TextInputModal(discord.ui.Modal):
    def __init__(self, title: str, step: int, answers: dict, onboarding: 'Onboarding'):
        # Set the modal title to the question
        super().__init__(title=title)
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

        # Add a text input field. You can add extra validation here if needed.
        self.input_field = discord.ui.TextInput(
            label=title, 
            placeholder="Type your answer here...",
            style=discord.TextStyle.short
        )
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        # Sla de ingevoerde waarde op in de actieve sessie
        self.answers[self.step] = self.input_field.value
        user_id = interaction.user.id
        if user_id in self.onboarding.active_sessions:
            self.onboarding.active_sessions[user_id]["answers"][self.step] = self.input_field.value

        # Give a short confirmation and proceed to the next question
        await interaction.response.send_message("Your response has been recorded.", ephemeral=True)
        # Call the next question
        await self.onboarding.send_next_question(interaction, step=self.step + 1, answers=self.answers)


class OnboardingView(discord.ui.View):
    """View for the onboarding flow."""
    def __init__(self, step: Optional[int] = None, answers: Optional[dict] = None, onboarding: Optional['Onboarding'] = None):
        super().__init__(timeout=None)
        self.step = step
        self.answers = answers if answers is not None else {}
        self.onboarding = onboarding
        self.view_id = uuid.uuid4().hex  # Unique ID for this view

class OnboardingButton(discord.ui.Button):
    """Button for single-select answers."""
    def __init__(self, label: str, value: str, step: int, onboarding: Onboarding):
        # Use the unique view_id in the custom_id
        # Note: 'self' is not available yet here, so we need to get this later via the view.
        # Therefore we make the custom_id dynamic in the callback or determine it in the OnboardingView.
        # One way is to set a placeholder in __init__ and override it afterwards.
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.value = value
        self.step = step
        self.onboarding = onboarding

    async def callback(self, interaction: discord.Interaction):
        # Indien de custom_id nodig is, kunnen we die nu dynamisch genereren.
        # Voor de logica zelf gebruiken we nu de gegevens uit de view, die een uniek view_id bevat.
        logger.info(f"🔘 Button clicked: {self.label} (value: {self.value})")
        user_id = interaction.user.id
        question_data = self.onboarding.questions[self.step]
        
        # Single-select: zet het antwoord
        # Als er een follow-up is voor deze keuze, bewaar zowel keuze als latere follow-up in een dict
        view = self.view
        if view is None:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("⚠️ Something went wrong. Please try again.", ephemeral=True)
            return
        onboarding_view = cast(OnboardingView, view)
        if self.value in question_data.get("followup", {}):
            onboarding_view.answers[self.step] = {"choice": self.value}
        else:
            onboarding_view.answers[self.step] = self.value
        if user_id in self.onboarding.active_sessions:
            self.onboarding.active_sessions[user_id]["answers"][self.step] = self.value

        # Controleer of er een follow-up modal nodig is
        if self.value in question_data.get("followup", {}):
            followup_cfg = question_data["followup"][self.value]
            followup_text = followup_cfg["question"] if isinstance(followup_cfg, dict) else str(followup_cfg)
            validate_email = isinstance(followup_cfg, dict) and followup_cfg.get("type") == "email"
            logger.info(f"📝 Follow-up triggered: {followup_text}")
            await interaction.response.send_modal(
                FollowupModal(
                    title="Follow-up Question",
                    question=followup_text,
                    step=self.step,
                    answers=onboarding_view.answers,
                    validate_email=validate_email,
                    onboarding=self.onboarding
                )
            )
            return

        # Activeer de confirm-knop
        for child in onboarding_view.children:
            if isinstance(child, ConfirmButton):
                child.disabled = False
                break
        await interaction.response.edit_message(view=onboarding_view)


class OnboardingSelect(discord.ui.Select):
    """Select menu voor multi-select vragen."""
    def __init__(self, step: int, options: list, onboarding: Onboarding, view_id: str):
        select_options = []
        for label, value in options:
            select_options.append(discord.SelectOption(label=label, value=value))
        # Bouw een unieke custom_id met behulp van het view_id en de stap
        custom_id = f"onboarding_select_{step}_{view_id}"
        super().__init__(
            placeholder="Selecteer een of meerdere opties...",
            min_values=1,
            max_values=len(options),
            options=select_options,
            custom_id=custom_id
        )
        self.step = step
        self.onboarding = onboarding

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"🔘 Select callback: geselecteerde waarden: {self.values}")
        user_id = interaction.user.id
        view = self.view
        if view is None:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("⚠️ Something went wrong. Please try again.", ephemeral=True)
            return
        onboarding_view = cast(OnboardingView, view)
        onboarding_view.answers[self.step] = self.values
        if user_id in self.onboarding.active_sessions:
            self.onboarding.active_sessions[user_id]["answers"][self.step] = self.values
        # Go directly to the next question for multi-select (no confirm needed)
        await self.onboarding.send_next_question(interaction, step=self.step + 1, answers=onboarding_view.answers)


class ConfirmButton(discord.ui.Button):
    """Button to confirm the current step and proceed."""
    def __init__(self, step: int, answers: dict, onboarding: Onboarding):
        # Create a unique custom_id using the view_id; we adjust this in the view.
        # Since we don't know 'self.view' yet in __init__, you can choose to
        # override or generate the custom_id later in the view.
        super().__init__(label="✅ Confirm", style=discord.ButtonStyle.success)
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in self.onboarding.active_sessions:
            logger.warning(f"⚠️ Geen actieve sessie voor {interaction.user.display_name}.")
            return
        logger.info(f'✅ {interaction.user.display_name} bevestigde stap {self.step}')
        session = self.onboarding.active_sessions[user_id]
        session["answers"].update(self.answers)
        await self.onboarding.send_next_question(interaction, step=self.step + 1, answers=session["answers"])

class FollowupModal(discord.ui.Modal):
    """Modal voor follow-up vragen waarbij de gebruiker tekst kan invoeren."""
    def __init__(self, title: str, question: str, step: int, answers: dict, validate_email: bool = False, onboarding: Optional['Onboarding'] = None):
        super().__init__(title=title)
        self.step = step
        self.answers = answers
        self.question = question
        self.validate_email = validate_email
        self.onboarding = onboarding
        self.input_field = discord.ui.TextInput(label=question, placeholder="Type your answer here...")
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        value = self.input_field.value.strip()

        # Emailvalidatie indien vereist
        if self.validate_email:
            bot_client = cast(commands.Bot, interaction.client)
            onboarding_cog: Onboarding = self.onboarding or cast(Onboarding, bot_client.get_cog("Onboarding"))
            if not onboarding_cog.EMAIL_REGEX.match(value):
                # Bied een retry-knop aan om opnieuw te proberen
                await interaction.response.send_message(
                    "❌ Invalid email format. Please try again.",
                    view=ReenterEmailView(step=self.step, answers=self.answers, onboarding=onboarding_cog),
                    ephemeral=True
                )
                return

        # Sla follow-up op naast de keuze
        existing = self.answers.get(self.step)
        if isinstance(existing, dict):
            existing["followup"] = value
            existing["followup_label"] = self.question
            self.answers[self.step] = existing
        else:
            self.answers[self.step] = {"choice": existing, "followup": value, "followup_label": self.question}

        # Update actieve sessie
        bot_client2 = cast(commands.Bot, interaction.client)
        onboarding = self.onboarding or cast(Onboarding, bot_client2.get_cog("Onboarding"))
        if user_id in onboarding.active_sessions:
            onboarding.active_sessions[user_id]["answers"][self.step] = self.answers[self.step]

        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("✅ Thanks! Moving to the next question...", ephemeral=True)
        await onboarding.send_next_question(interaction, step=self.step + 1, answers=self.answers)


class ReenterEmailView(discord.ui.View):
    def __init__(self, step: int, answers: dict, onboarding: Onboarding):
        super().__init__(timeout=60)
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

    @discord.ui.button(label="Re-enter email", style=discord.ButtonStyle.primary)
    async def reenter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            FollowupModal(
                title="Email Address",
                question="Please enter your email address",
                step=self.step,
                answers=self.answers,
                validate_email=True,
                onboarding=self.onboarding,
            )
        )

async def setup(bot: commands.Bot):
    cog = Onboarding(bot)
    await bot.add_cog(cog)
    await cog.setup_database()  # Zorg dat de database correct wordt opgezet
