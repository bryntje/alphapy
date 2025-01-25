import discord
import asyncio
from discord.ext import commands

# 🛠️ SERVER-INSTELLINGEN (Vervang met jouw waarden)
TOKEN = "MTMzMjQzNTE2MjczMDA3MDA4Nw.GfJrEW.rZjFmpGlanQqNgXJOz0yz8jEgpwpyECjD6fOJE"
GUILD_ID = 1330201976717312081  # De ID van jouw Discord-server
MEE6_MESSAGE_ID = 1332449426354081814  # ID van het MEE6 reaction role bericht
ROLE_ID = 1330471273364721664  # ID van de verificatierol
LOG_CHANNEL_ID = 1330492696078319696  # ID van het kanaal waar verificaties worden gelogd

# ✅ Intents inschakelen
intents = discord.Intents.default()
intents.message_content = True  
intents.reactions = True
intents.guilds = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 📜 VERIFICATIE FLOW MET KNOPPEN
class StartVerificationView(discord.ui.View):
    """Start de verificatievragen bij klikken op 'Start'."""
    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member

    @discord.ui.button(label="Start ✅", style=discord.ButtonStyle.green, custom_id="start_verification")
    async def start_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Direct starten met de verificatievragen."""
        await interaction.response.defer()  # ✅ Correcte manier om de interactie te deferren
        await VerificationRulesView(self.member, 0).send_next_rule(interaction)  # ✅ Direct de vragen starten

class NextVerificationView(discord.ui.View):
    """Volgende stap van verificatie."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Continue ✅", style=discord.ButtonStyle.green, custom_id="continue_verification")
    async def continue_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🚫 No Spam or Promotions",
            description="Advertising or spamming is strictly forbidden in Alphapips™.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Click 'Continue' to proceed.")
        await interaction.response.edit_message(embed=embed, view=FinalVerificationView())

class FinalVerificationView(discord.ui.View):
    """Laatste verificatiestap, waarna een DM wordt verstuurd."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept & Verify ✅", style=discord.ButtonStyle.green, custom_id="accepted_final")
    async def accepted_final(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(GUILD_ID)
        member = await guild.fetch_member(interaction.user.id) if guild else None

        if not member:
            print(f"❌ ERROR: Kan 'Member' object niet vinden voor {interaction.user.id}")
            await interaction.response.send_message("❌ Error: Could not verify you. Contact an admin.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Verification Complete",
            description="You are now verified and have access to Alphapips™!",
            color=discord.Color.green()
        )

        try:
            await member.send(embed=embed)  # 🚀 Direct een DM sturen
            await interaction.response.send_message("✅ Check your DMs for confirmation!", ephemeral=True)
        except discord.Forbidden:
            print(f"❌ ERROR: Kan geen DM sturen naar {member.display_name}. DM’s zijn mogelijk uitgeschakeld.")
            await interaction.response.send_message("❌ I can't send you a DM. Please enable DMs and try again.", ephemeral=True)

class StartFormView(discord.ui.View):
    def __init__(self, user, bot):
        super().__init__(timeout=None)  # Timeout=None betekent dat de view altijd actief blijft
        self.user = user
        self.bot = bot

    @discord.ui.button(label="🚀 Start Form", style=discord.ButtonStyle.green, custom_id="start_form")
    async def start_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start het onboarding formulier wanneer de knop wordt aangeklikt."""
        await interaction.response.defer()
        form_view = OnboardingFormView(interaction.user, self.bot, key="onboarding")

        embed = discord.Embed(
            title="📋 Step 1: First Question",
            description="Let's begin your onboarding process!",
            color=discord.Color.blue()
        )

        await interaction.message.edit(embed=embed, view=form_view)  # Update met eerste vraag
        await form_view.send_next_question(interaction)  # Stuur de eerste vraag


class VerificationRulesView(discord.ui.View):
    """Verifieert gebruikers stap voor stap op basis van kernwaarden."""
    def __init__(self, member, current_step=0):
        super().__init__(timeout=None)
        self.member = member
        self.current_step = current_step
        self.core_values = [
            ("📜 Core Value 1: Respect Others", "We value a positive and supportive environment."),
            ("📜 Core Value 2: No Spam or Promotions", "External links and advertisements are not allowed."),
            ("📜 Core Value 3: Educational Content Only", "Only share educational content within the community."),
            ("📜 Core Value 4: No Financial Advice", "We don't provide financial advice, only education."),
            ("📜 Core Value 5: Ambassador Content Sharing", "Only ambassadors may share content externally."),
            ("📜 Core Value 6: Compliance & Expectations", "Failure to comply with these principles may result in removal.")
        ]

    async def send_next_rule(self, interaction):
        """Verstuurt de volgende regel en update het bericht."""
        if self.current_step < len(self.core_values):
            title, description = self.core_values[self.current_step]

            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Step {self.current_step + 1} of {len(self.core_values)}")

            # Verwijder oude knoppen om duplicaten te voorkomen
            self.clear_items()
            button = discord.ui.Button(label="✅ Accept", style=discord.ButtonStyle.green, custom_id="accept_rule")

            async def callback(interaction: discord.Interaction):
                """Verwerkt de knopklik en gaat door naar de volgende stap."""
                await interaction.response.defer()  # Zorgt ervoor dat de interactie niet mislukt
                self.current_step += 1
                await self.send_next_rule(interaction)

            button.callback = callback
            self.add_item(button)

            try:
                await interaction.message.edit(embed=embed, view=self)  # Update het bericht in plaats van een nieuw bericht te sturen
            except discord.errors.InteractionResponded:
                print("⚠️ Interaction already responded to. Skipping update.")
        else:
            await self.finish_verification(interaction)  # Start het onboarding-formulier als de laatste regel is geaccepteerd

    async def finish_verification(self, interaction):
        """Laatste stap van de verificatie, start het onboarding-formulier nadat de verificatie is voltooid."""

        # Update het bericht dat de verificatie is voltooid
        embed = discord.Embed(
            title="✅ Verification Complete",
            description="You are now verified! Please fill out the onboarding form.",
            color=discord.Color.green()
        )

        await interaction.message.edit(embed=embed, view=None)  # Verwijder verificatieknoppen

        # Maak het onboarding-formulier bericht en voeg een Start-knop toe
        form_embed = discord.Embed(
            title="📋 Onboarding Form",
            description="Let's complete your onboarding form step by step.",
            color=discord.Color.blue()
        )

        # ✅ Gebruik StartFormView om de knop correct te laten werken!
        await interaction.message.edit(embed=form_embed, view=StartFormView(interaction.user, bot))


        async def start_form_callback(interaction: discord.Interaction):
            """Verwerkt de klik op de Start Form-knop en start het onboarding-formulier."""
            await interaction.response.defer()
            form_view = OnboardingFormView(interaction.user, self.bot, key="onboarding")

            embed = discord.Embed(
                title="📋 Step 1: First Question",
                description="Let's begin your onboarding process!",
                color=discord.Color.blue()
            )

            await interaction.message.edit(embed=embed, view=form_view)  # Update met eerste vraag
            await form_view.send_next_question(interaction)  # Stuur de eerste vraag

        start_button = discord.ui.Button(label="🚀 Start Form", style=discord.ButtonStyle.green, custom_id="start_form")
        start_button.callback = start_form_callback  # Zonder self!



    async def start_onboarding_form(self, interaction):
        """Start the onboarding form after verification is completed."""

        # ✅ Create an instance of OnboardingFormView and pass bot
        form_view = OnboardingFormView(interaction.user, self.bot, key="onboarding")

        embed = discord.Embed(
            title="📋 Step 1: First Question",
            description="Let's begin your onboarding process!",
            color=discord.Color.blue()
        )

        # ✅ Edit the message to show the first onboarding question
        await interaction.message.edit(embed=embed, view=form_view)

        # ✅ Move to the first question immediately
        await form_view.send_next_question(interaction)

class MultipleChoiceView(discord.ui.View):
    def __init__(self, form, key, options, allow_multiple=False):
        super().__init__(timeout=None)

        self.form = form
        self.key = key
        self.selected_options = set()
        self.allow_multiple = allow_multiple

        print(f"DEBUG: Creating Persistent MultipleChoiceView for {key} with options: {options}")

        for option_text, option_id in options:
            button = discord.ui.Button(
                label=option_text,
                style=discord.ButtonStyle.primary,
                custom_id=f"{key}_{option_id}"
            )
            button.callback = self.create_callback(option_text, option_id)
            self.add_item(button)
            print(f"DEBUG: Added button {button.label} with custom_id {button.custom_id}")

        # Alleen een Confirm-knop toevoegen als meerdere keuzes mogelijk zijn
        if self.allow_multiple:
            confirm_button = discord.ui.Button(
                label="✅ Confirm",
                style=discord.ButtonStyle.success,
                custom_id=f"confirm_{key}"
            )
            confirm_button.callback = self.confirm_selection
            self.add_item(confirm_button)
            print(f"✅ Added Confirm Button with custom_id confirm_{key}")

    def create_callback(self, option_text, option_id):
        async def callback(interaction: discord.Interaction):
            print(f"DEBUG: Button {option_text} clicked!")
            await interaction.response.defer()

            if self.allow_multiple:
                if option_id in self.selected_options:
                    self.selected_options.remove(option_id)
                    print(f"❌ Removed {option_id} from selection")
                else:
                    self.selected_options.add(option_id)
                    print(f"✅ Added {option_id} to selection")
            else:
                self.form.answers[self.key] = option_id
                self.form.current_step += 1
                await self.form.send_next_question(interaction)

        return callback

    async def confirm_selection(self, interaction: discord.Interaction):
        print(f"DEBUG: Current answers: {self.form.answers}")
        """Bevestigt de geselecteerde opties en gaat door naar de volgende vraag."""
        if self.selected_options:
            self.form.answers[self.key] = list(self.selected_options)
            print(f"✅ Confirmed selection for {self.key}: {self.selected_options}")

            self.form.current_step += 1

            # ✅ Controleer of interactie al verwerkt is
            if interaction.response.is_done():
                print("⚠️ WARNING: Interaction response is already done! Using followup instead.")
                await interaction.followup.send("Processing next question...", ephemeral=True)
            else:
                print("✅ Interaction is still open. Sending next question.")
                await interaction.response.defer()  # Zorg ervoor dat de interactie niet verloopt

            # ✅ Stuur de volgende vraag
            await self.form.send_next_question(interaction)

        else:
            print("⚠️ No options selected!")
            await interaction.response.send_message("⚠️ Please select at least one option before confirming.", ephemeral=True)


    async def confirm_callback(self, interaction: discord.Interaction):
        print(f"DEBUG: Confirm button clicked for {self.key}")
        if self.selected_options:
            self.form.answers[self.key] = list(self.selected_options)
            print(f"✅ Confirmed selection for {self.key}: {self.selected_options}")
        else:
            print(f"⚠️ No options selected!")

        self.form.current_step += 1
        await self.form.send_next_question(interaction)


class OnboardingFormView(discord.ui.View):
    def __init__(self, member: discord.Member, bot: discord.Client, key: str, timeout=180):
        super().__init__(timeout=timeout)
        self.member = member
        self.key = key
        self.bot = bot  # Save the bot object to access later
        self.current_step = 0
        self.answers = {}
        self.questions = [
            ("🌟 How did you hear about Alphapips™?", "q1", [
                ("Invited by a friend", "friend"),
                ("Social Media", "social"),
                ("Event / Presentation", "event"),
                ("Other", "other")
            ]),
            ("👫 Enter name of inviter", "q2", None),  # Open veld als "friend" is gekozen
            ("✅ Do you want to receive updates?", "q3", [
                ("Yes, keep me updated!", "yes"),
                ("No, I don’t want updates.", "no")
            ]),
            ("📧 Enter Email", "q4", None),  # Alleen tonen als ze 'yes' kiezen bij q3
            ("📜 What do you want to achieve with Alphapips™?", "q5", [
                ("🚀 Financial Knowledge", "finance"),
                ("💡 Learn Trading", "trading"),
                ("🔗 Networking", "networking"),
                ("🌟 Personal Growth", "growth"),
                ("✨ Other", "other")
            ]),
            ("📊 Which markets are you interested in?", "q6", [
                ("📈 Forex", "forex"),
                ("📉 Crypto", "crypto"),
                ("🏛️ Stocks", "stocks"),
                ("🌍 Indices", "indices"),
                ("💹 Commodities", "commodities")
            ]),
            ("💡 What is your trading experience level?", "q7", [
                ("🆕 Beginner", "beginner"),
                ("📈 Intermediate", "intermediate"),
                ("💼 Advanced", "advanced")
            ]),
            ("🔧 What tools are you currently using?", "q8", [
                ("🖥️ TradingView", "tradingview"),
                ("📊 MetaTrader", "metatrader"),
                ("📉 NinjaTrader", "ninjatrader"),
                ("🔍 Other", "other")
            ])
        ]


    def get_start_embed(self):
        return discord.Embed(
            title="📋 Verification Form",
            description="Let's complete your onboarding form step by step.",
            color=discord.Color.blue()
        )

    async def ask_for_input(self, interaction: discord.Interaction, question_text: str, question_key: str):
        """Waits for user input and stores it properly."""

        # ✅ Only defer if interaction hasn't been responded to
        if not interaction.response.is_done():
            await interaction.response.defer()

        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel

        try:
            # ✅ Wait for the user's response (max 60 seconds)
            message = await self.bot.wait_for("message", check=check, timeout=60.0)
            user_input = message.content  # ✅ Get the user's input

            # ✅ Save the user's answer
            self.answers[question_key] = user_input

            # ✅ Delete the user’s response to keep the chat clean
            if interaction.guild is not None:  # Alleen verwijderen als het GEEN DM is
                await message.delete()
            else:
                print("⚠️ WARNING: Cannot delete messages in a DM. Skipping delete.")


            # ✅ Move to the next question
            self.current_step += 1
            await self.send_next_question(interaction)

        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ You took too long to respond. Restarting the form.", ephemeral=True)
            self.current_step = 0
            await self.send_next_question(interaction)


    async def force_refresh_view(interaction, embed, view):
        """Forcibly refreshes the message with a new view to prevent Discord caching issues."""
        await interaction.message.edit(embed=embed, view=None)  # Eerst de view verwijderen
        await asyncio.sleep(1)  # Kort wachten zodat Discord het verwerkt
        await interaction.message.edit(embed=embed, view=view)  # Nu de nieuwe view toepassen




    async def send_next_question(self, interaction):
        """Sends the next onboarding question dynamically, handling both multiple-choice and text input."""
        print(f"DEBUG: send_next_question() called for step {self.current_step}/{len(self.questions)}")

        if self.current_step < len(self.questions):
            question_text, key, options = self.questions[self.current_step]
            is_text_input = options is None  # ✅ Controleert of de vraag tekstinput of multiple-choice is

            # ✅ Skip email question correctly
            if key == "q4" and self.answers.get("q3") != "yes":
                print("DEBUG: Skipping email question since user chose 'No' for updates.")
                self.current_step += 1  # Advance to next step
                return await self.send_next_question(interaction)  # Continue to next question **without exiting the function**

            allow_multiple = key in ["q5", "q6", "q7", "q8"]  # ⬅️ Meervoudige keuze alleen voor deze vragen
            view = MultipleChoiceView(self, key, options, allow_multiple=allow_multiple) if not is_text_input else discord.ui.View(timeout=None)

            embed = discord.Embed(
                title="📋 Onboarding Form",
                description=question_text,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Please type your answer below and press Enter." if is_text_input else "Click an option below.")

            # 🔥 Debugging - Controleer of knoppen correct worden aangemaakt
            print(f"DEBUG: Created View for question {key} - Contains {len(view.children)} buttons")
            for button in view.children:
                print(f"✅ Button: {button.label} - Custom ID: {button.custom_id}")

            # ✅ Controleer of interactie al verwerkt is
            if interaction.response.is_done():
                print("⚠️ WARNING: Interaction response is already done! Using followup instead.")
                await interaction.followup.send(embed=embed, view=view)
            else:
                print("✅ Interaction is still open. Editing response.")
                await interaction.response.defer()
                await interaction.response.edit_message(embed=embed, view=view)

            # ✅ Laatste debugging voor verzending
            print(f"🔥 DEBUG: FINAL View contains {len(view.children)} buttons")
            for button in view.children:
                print(f"✅ Button Label: {button.label} - Custom ID: {button.custom_id}")

            # ✅ Handle text input indien nodig
            if is_text_input:
                await self.ask_for_input(interaction, question_text, key)
            return  # **Belangrijk! Zorg ervoor dat het hier stopt totdat input wordt gegeven**

        # **Als alle vragen beantwoord zijn, beëindig onboarding correct**
        await self.finish_form(interaction)




    async def finish_form(self, interaction):
        """Verstuurt antwoorden naar het verificatiekanaal, de gebruiker en kent een rol toe."""
        print("🎉 Onboarding complete! Assigning role...")
    
        answers_text = "\n".join([f"**{k}:** {v}" for k, v in self.answers.items()])
        embed = discord.Embed(title="✅ Onboarding Complete", description=answers_text, color=discord.Color.green())
    
        # ✅ Verstuur een bericht naar het logkanaal
        guild = interaction.client.get_guild(GUILD_ID)
        if guild:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"✅ User {interaction.user} has completed the onboarding!", embed=embed)
            
            # ✅ Rol toekennen
            role = guild.get_role(ROLE_ID)
            member = guild.get_member(interaction.user.id)
            if role and member:
                await member.add_roles(role)
                print(f"✅ Assigned role {role.name} to {member.display_name}")
        else:
            print("⚠️ WARNING: Guild not found! Cannot assign role or log verification.")
        
        # ✅ Stuur een samenvatting naar de gebruiker
        await interaction.user.send(embed=embed)
        print(f"✅ Sent DM to {interaction.user.display_name} with onboarding summary.")



@bot.command()
async def testbutton(ctx):
    """Stuurt een testbericht met een knop om te kijken of knoppen WEL werken."""
    view = discord.ui.View()
    
    button = discord.ui.Button(label="Click Me!", style=discord.ButtonStyle.green, custom_id="test_button")

    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_message("✅ Button clicked!", ephemeral=True)

    button.callback = button_callback
    view.add_item(button)

    await ctx.send("Click the button below:", view=view)



@bot.event
async def on_raw_reaction_add(payload):
    """Luistert naar reacties op het MEE6-verificatiebericht en start de verificatievragen."""
    
    if payload.message_id != MEE6_MESSAGE_ID:
        return

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ ERROR: Guild niet gevonden.")
        return

    member = await guild.fetch_member(payload.user_id)  
    if not member or member.bot:  
        return

    try:
        embed = discord.Embed(
            title="🔍 Verification Required",
            description="Before gaining access to Alphapips™, please accept our core values by clicking 'Start'.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Click 'Start' to begin.")

        await member.send(embed=embed, view=StartVerificationView(member))
    except discord.Forbidden:
        print(f"❌ ERROR: Kan geen DM sturen naar {member.display_name}. DM’s zijn mogelijk uitgeschakeld.")



@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")

    # Register persistent views correctly
    bot.add_view(StartVerificationView(None))
    bot.add_view(VerificationRulesView(None))
    dummy_form = OnboardingFormView(member=None, bot=bot, key="dummy")
    bot.add_view(MultipleChoiceView(dummy_form, "dummy", [("Test", "test")]))

    print("✅ Views are now registered!")



bot.run(TOKEN)

