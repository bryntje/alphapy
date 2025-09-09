import discord
from discord.ext import commands
import json
import logging
import uuid
import re
from typing import Optional, Dict, Any, cast
from config import ROLE_ID, LOG_CHANNEL_ID
import asyncpg
import config

# Configureer de logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

class Onboarding(commands.Cog):
    """Cog die het onboarding-proces voor nieuwe gebruikers beheert."""
    
    def __init__(self, bot):
        self.bot = bot
        # Houd per gebruiker de huidige stap en antwoorden bij.
        self.active_sessions = {}  # { user_id: {"step": int, "answers": {}} }
        # Regex voor emailvalidatie
        self.EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")

        # Nieuwe, compacte onboarding flow (4 vragen)
        self.questions = [
            {
                "question": "📣 How did you hear about AlphaPips?",
                "options": [
                    ("Invited by a friend", "friend"),
                    ("Social Media", "social"),
                    ("Event / Presentation", "event")
                ],
                "followup": {
                    "friend": {"question": "Who invited you?"},
                    "social": {"question": "Which platform?"},
                    "event": {"question": "Name of the event?"}
                }
            },
            {
                "question": "💼 Which opportunities are you most interested in?",
                "options": [
                    ("🔺 Forex", "forex"),
                    ("💰 Crypto", "crypto"),
                    ("📈 Stocks", "stocks"),
                    ("📸 UGC", "ugc"),
                    ("🛒 E-commerce", "ecommerce"),
                    ("🤝 Network Marketing", "network_marketing")
                ],
                "multiple": True
            },
            {
                "question": "🧠 Do you have a ZiNRAi membership?",
                "options": [
                    ("✅ Yes", "yes"),
                    ("❌ No", "no")
                ]
            },
            {
                "question": "📞 Would you like to have an introduction call?",
                "options": [
                    ("✅ Yes", "yes"),
                    ("❌ No", "no")
                ],
                "followup": {
                    "yes": {"question": "Please enter your email address", "type": "email"}
                }
            }
        ]
        
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
        self.db = await asyncpg.create_pool(config.DATABASE_URL)
        async with self.db.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS onboarding (
                    user_id BIGINT PRIMARY KEY,
                    responses JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')

    async def send_next_question(self, interaction: discord.Interaction, step: int = 0, answers: Optional[dict] = None):
        user_id = interaction.user.id

        # Zorg dat er een actieve sessie is voor deze gebruiker
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {"step": 0, "answers": {}}
        session = self.active_sessions[user_id]

        # Gebruik bestaande antwoorden of update de sessie
        if answers is None:
            answers = session["answers"]
        else:
            session["answers"] = answers

        # Als alle vragen beantwoord zijn, verwerk dan de afronding
        if step >= len(self.questions):
            logger.info(f"🎉 Onboarding completed for {interaction.user.display_name}!")

            summary_embed = discord.Embed(
                title="📜 Onboarding Summary",
                description=f"Here is a summary of your onboarding responses, {interaction.user.display_name}:",
                color=discord.Color.blue()
            )
            for idx, question in enumerate(self.questions):
                raw_answer = answers.get(idx, "No response")
                answer_text = self._format_answer(question, raw_answer)
                summary_embed.add_field(name=f"**{question['question']}**", value=f"➜ {answer_text}", inline=False)

            # Verstuur de samenvatting als ephemeral bericht naar de gebruiker
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=summary_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=summary_embed, ephemeral=True)

            # Sla de onboarding data op in de database
            await self.store_onboarding_data(user_id, answers)

            # Bouw en verstuur een log-embed naar het logkanaal
            log_embed = discord.Embed(
                title="📝 Onboarding Log",
                description=f"**User:** {interaction.user} ({interaction.user.id})",
                color=discord.Color.green()
            )
            for idx, question in enumerate(self.questions):
                raw_answer = answers.get(idx, "No response")
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

        # Haal de huidige vraag op
        q_data = self.questions[step]

        # Als deze vraag een vrije tekstinvoer vereist, stuur dan een modal
        if q_data.get("input"):
            modal = TextInputModal(title=q_data["question"], step=step, answers=answers, onboarding=self)
            await interaction.response.send_modal(modal)
            return

        # Anders, bouw een embed en view voor de vraag met opties
        embed = discord.Embed(title="📝 Onboarding Form", description=q_data["question"], color=discord.Color.blue())
        view = OnboardingView(step=step, answers=answers, onboarding=self)

        if q_data.get("multiple"):
            # Voeg een select menu toe voor multi-select vragen
            view.add_item(OnboardingSelect(step=step, options=q_data["options"], onboarding=self, view_id=view.view_id))
        else:
            # Voeg knoppen toe voor single-select vragen
            for label, value in q_data["options"]:
                view.add_item(OnboardingButton(label=label, value=value, step=step, onboarding=self))

        # Voeg een confirm-knop toe die pas wordt ingeschakeld als er een keuze is gemaakt
        confirm_button = ConfirmButton(step, answers, self)
        confirm_button.disabled = True
        view.add_item(confirm_button)

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def store_onboarding_data(self, user_id, responses):
        """Slaat onboarding data op in de database."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO onboarding (user_id, responses)
                VALUES ($1, $2)
                ON CONFLICT(user_id) DO UPDATE SET responses = $2;
                """,
                user_id, json.dumps(responses)
            )
        logger.info(f"✅ Onboarding data opgeslagen voor {user_id}")

class TextInputModal(discord.ui.Modal):
    def __init__(self, title: str, step: int, answers: dict, onboarding: 'Onboarding'):
        # Stel de titel van de modal in op de vraag
        super().__init__(title=title)
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

        # Voeg een tekstinvoerveld toe. Je kunt hier eventueel extra validatie toevoegen.
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

        # Geef een korte bevestiging en ga verder met de volgende vraag
        await interaction.response.send_message("Your response has been recorded.", ephemeral=True)
        # Roep de volgende vraag op
        await self.onboarding.send_next_question(interaction, step=self.step + 1, answers=self.answers)


class OnboardingView(discord.ui.View):
    """View voor de onboarding-flow."""
    def __init__(self, step: Optional[int] = None, answers: Optional[dict] = None, onboarding: Optional['Onboarding'] = None):
        super().__init__(timeout=None)
        self.step = step
        self.answers = answers if answers is not None else {}
        self.onboarding = onboarding
        self.view_id = uuid.uuid4().hex  # Uniek ID voor deze view

class OnboardingButton(discord.ui.Button):
    """Knop voor single-select antwoorden."""
    def __init__(self, label: str, value: str, step: int, onboarding: Onboarding):
        # Gebruik nu het unieke view_id in de custom_id
        # Merk op: 'self' is hier nog niet beschikbaar, dus we moeten dit later via de view ophalen.
        # Daarom maken we de custom_id dynamisch in de callback of we bepalen dit in de OnboardingView.
        # Eén manier is om in de __init__ alvast een placeholder te zetten en daarna te overschrijven.
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
        # Activeer de confirm-knop als er minstens één optie is geselecteerd
        for child in onboarding_view.children:
            if isinstance(child, ConfirmButton):
                child.disabled = not bool(self.values)
                break
        await interaction.response.edit_message(view=onboarding_view)


class ConfirmButton(discord.ui.Button):
    """Knop om de huidige stap te bevestigen en door te gaan."""
    def __init__(self, step: int, answers: dict, onboarding: Onboarding):
        # Maak een unieke custom_id met behulp van het view_id; we passen dit aan in de view.
        # Omdat we 'self.view' nog niet kennen in __init__, kun je ervoor kiezen om
        # de custom_id later in de view te overschrijven of te genereren.
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
