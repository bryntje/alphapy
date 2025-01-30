import discord
from discord.ext import commands
from config import ROLE_ID


class Onboarding(commands.Cog):
    """Cog managing the onboarding process for new users."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}  # Houdt bij welke gebruiker met onboarding bezig is
        self.questions = [
            {
                "question": "🌟 How did you hear about Alphapips?",
                "options": [
                    ("Invited by a friend", "friend"),
                    ("Social Media", "social"),
                    ("Event / Presentation", "event"),
                    ("Other", "other")
                ],
                "followup": {
                    "friend": "Who invited you?"
                }
            },
            {
                "question": "🙋‍♂️ What do you want to achieve with Alphapips?",
                "options": [
                    ("🚀 Financial Knowledge", "finance"),
                    ("💡 Learn Trading", "trading"),
                    ("🔗 Networking", "networking"),
                    ("🌟 Personal Growth", "growth"),
                    ("✨ Other", "other")
                ]
            },
            {
                "question": "📊 How experienced are you in trading?",
                "options": [
                    ("🔰 Beginner (0-3 months)", "beginner"),
                    ("📈 Intermediate (3-12 months)", "intermediate"),
                    ("🚀 Advanced (1+ year)", "advanced")
                ]
            },
            {
                "question": "💳 Do you already have an iGenius membership?",
                "options": [
                    ("✅ Yes", "yes"),
                    ("❌ No", "no")
                ]
            },
            {
                "question": "📈 Which markets are you most interested in?",
                "options": [
                    ("🔺 Forex", "forex"),
                    ("💰 Crypto", "crypto"),
                    ("📈 Equities", "equities"),
                    ("🔍 Other", "other")
                ]
            },
            {
                "question": "📺 Are you interested in learning from live trading sessions?",
                "options": [
                    ("✅ Yes", "yes"),
                    ("❌ No", "no")
                ]
            },
            {
                "question": "🚀 Would you like to be part of the Alphapips Growth & Leadership program?",
                "options": [
                    ("✅ Yes", "yes"),
                    ("❌ No", "no")
                ]
            }
        ]

    async def send_next_question(self, interaction: discord.Interaction, step: int = 0, answers: dict = None):
        """Sends the next question in the onboarding process for the specific user."""
        user_id = interaction.user.id  # Zorg dat we altijd werken met de juiste gebruiker

        # ✅ Gebruik een aparte sessie per gebruiker
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {"step": 0, "answers": {}}

        session = self.active_sessions[user_id]  # Laad de sessie van deze gebruiker

        if answers is None:
            answers = session["answers"]  # Haal de antwoorden van deze gebruiker op

        # ✅ Controleer of de step niet buiten de lijst valt
        if step >= len(self.questions):
            print(f"🎉 Onboarding completed for {interaction.user.display_name}!")

            # ✅ Stuur bevestigingsbericht
            if interaction.response.is_done():
                print("⚠️ Interaction already completed, using followup.")
                await interaction.followup.send("✅ Onboarding completed! Welcome to AlphaPips! 🚀", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Onboarding completed! Welcome to AlphaPips! 🚀", ephemeral=True)


            # ✅ Geef de gebruiker de rol
            guild = interaction.guild
            member = guild.get_member(interaction.user.id)

            if member:
                role = guild.get_role(ROLE_ID)
                if role:
                    await member.add_roles(role)
                    print(f"✅ Role '{role.name}' assigned to {member.display_name}")
                else:
                    print(f"⚠️ Role ID '{ROLE_ID}' not found.")
            else:
                print("⚠️ Member not found.")

            # ✅ Verwijder de sessie zodra onboarding klaar is
            del self.active_sessions[interaction.user.id]
            print(f"🗑️ Onboarding session removed for {interaction.user.display_name}")

            return  # Stop hier, want onboarding is klaar


        q_data = self.questions[step]
        embed = discord.Embed(title="📝 Onboarding Form", description=q_data["question"], color=discord.Color.blue())

        # If a follow-up is required, show a text input modal
        if answers and list(answers.values())[-1] in q_data.get("followup", {}):
            followup_text = q_data["followup"][list(answers.values())[-1]]
            print(f"📝 Follow-up triggered: {followup_text}")  # ✅ Debug log

            if interaction.response.is_done():
                print("⚠️ Interaction is al voltooid, follow-up modal kan niet worden gestuurd.")
                await interaction.followup.send("⚠️ Error: Could not send follow-up modal.", ephemeral=True)
                return

            print("🚀 Sending Follow-up Modal...")
            await interaction.response.send_modal(FollowupModal(title="Follow-up Question", question=followup_text, step=step, answers=answers))
            print("✅ Follow-up modal sent!")
            return

        view = OnboardingView(step, answers, self)

        for label, value in q_data["options"]:
            view.add_item(OnboardingButton(label=label, value=value, step=step, onboarding=self))

        print(f"📌 Adding ConfirmButton to view at step {step}")
        confirm_button = ConfirmButton(step, answers, self)
        view.add_item(confirm_button)  # ✅ Confirm button before progressing

        try:
            message = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = message  # ✅ Forceer de view om gekoppeld te blijven aan het bericht
        except discord.errors.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)



class OnboardingView(discord.ui.View):
    """Interactive buttons for onboarding."""
    def __init__(self, step: int, answers: dict, onboarding: Onboarding):
        super().__init__(timeout=None)
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

class OnboardingButton(discord.ui.Button):
    """Button for selecting an answer."""
    def __init__(self, label: str, value: str, step: int, onboarding: Onboarding):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=value)
        self.value = value
        self.step = step
        self.onboarding = onboarding

    async def callback(self, interaction: discord.Interaction):
        print(f"🔘 Button clicked: {self.label} (value: {self.value})")
        self.view.answers[self.step] = self.value  # Save answer

        onboarding = interaction.client.get_cog("Onboarding")

        # Check of een follow-up nodig is
        question_data = onboarding.questions[self.step]
        if self.value in question_data.get("followup", {}):
            followup_text = question_data["followup"][self.value]
            print(f"📝 Follow-up triggered: {followup_text}")

            if interaction.response.is_done():
                print("⚠️ Interaction is already responded, sending follow-up via followup.send()")
                await interaction.followup.send("⚠️ Error: Could not send follow-up modal.", ephemeral=True)
                return

            print("🚀 Sending Follow-up Modal...")
            await interaction.response.send_modal(FollowupModal(title="Follow-up Question", question=followup_text, step=self.step, answers=self.view.answers))
            print("✅ Follow-up modal sent!")
            return

        # ✅ In plaats van direct naar de volgende vraag te gaan, wacht op "Confirm"
        await interaction.response.defer()


class ConfirmButton(discord.ui.Button):
    """Button to confirm answers before moving to the next step."""
    def __init__(self, step: int, answers: dict, onboarding: Onboarding):
        super().__init__(label="✅ Confirm", style=discord.ButtonStyle.success, custom_id="confirm")
        self.step = step
        self.answers = answers
        self.onboarding = onboarding

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id  # Zorg dat de juiste gebruiker wordt verwerkt

        if user_id not in self.onboarding.active_sessions:
            print(f"⚠️ Geen actieve sessie voor {interaction.user.display_name}. Stop confirm.")
            return

        session = self.onboarding.active_sessions[user_id]  # Haal de sessie van deze gebruiker op
        # ConfirmButton slaat geen waarde op, dus we slaan hier niks op
        print(f'✅ {interaction.user.display_name} bevestigde stap {self.step}')

        # ✅ Stuur de gebruiker naar de volgende vraag in zijn eigen sessie
        await self.onboarding.send_next_question(interaction, step=self.step + 1, answers=session["answers"])



class FollowupModal(discord.ui.Modal):
    """Modal for follow-up text input."""
    def __init__(self, title: str, question: str, step: int, answers: dict):
        super().__init__(title=title)
        self.step = step
        self.answers = answers
        self.question = question

        self.input_field = discord.ui.TextInput(label=question, placeholder="Type your answer here...")
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        self.answers[self.step] = self.input_field.value  # Store response
        onboarding = interaction.client.get_cog("Onboarding")

        # ✅ Voorkom dat interactie al een antwoord heeft gegeven
        await interaction.response.defer(ephemeral=True)  
        await interaction.followup.send("✅ Thanks! Moving to the next question...", ephemeral=True)

        await onboarding.send_next_question(interaction, step=self.step + 1, answers=self.answers)


async def setup(bot):
    await bot.add_cog(Onboarding(bot))
