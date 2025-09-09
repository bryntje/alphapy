import discord
from discord.ext import commands
import config

class StartOnboardingView(discord.ui.View):
    """View met een knop om direct de onboarding te starten."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartOnboardingButton())

class StartOnboardingButton(discord.ui.Button):
    """Knop om de regels te accepteren en direct de onboarding te starten."""
    def __init__(self):
        # Gebruik een vaste custom_id zodat dit als persistent view herkend wordt.
        super().__init__(label="🚀 Start Onboarding", style=discord.ButtonStyle.success, custom_id="start_onboarding")
        
    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        # Start met de regels
        rules_view = RuleAcceptanceView(member)
        await interaction.response.send_message(
            "📜 Please accept each rule one by one before proceeding:",
            view=rules_view,
            ephemeral=True  # Houd het bericht privé
        )

class RuleAcceptanceView(discord.ui.View):
    """View waarin gebruikers regels één voor één moeten accepteren voordat ze doorgaan naar onboarding."""
    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member
        self.current_rule = 0
        self.accepted_rules = set()
        self.rules = [
            ("🛡️ Respect Others", "Stay constructive & professional."),
            ("🚫 No Spam or Promotions", "External links, ads, and spam are forbidden."),
            ("📚 Educational Content Only", "Do not share content outside Alphapips™."),
            ("🌟 Ambassador Content Sharing", "Only approved ambassadors may share externally."),
            ("💰 No Financial Advice", "Alphapips™ provides education, not financial advice.")
        ]
        self.update_buttons()

    def update_buttons(self):
        """Update de knoppen zodat alleen de huidige regel getoond wordt."""
        self.clear_items()
        if self.current_rule < len(self.rules):
            rule_text, _ = self.rules[self.current_rule]
            self.add_item(RuleButton(rule_index=self.current_rule, rule_text=rule_text, view=self))
        elif len(self.accepted_rules) == len(self.rules):
            self.add_item(FinalAcceptButton())

class RuleButton(discord.ui.Button):
    """Knop om een regel te accepteren."""
    def __init__(self, rule_index: int, rule_text: str, view: RuleAcceptanceView):
        super().__init__(label="✅ I Accept", style=discord.ButtonStyle.primary, custom_id=f"rule_{rule_index}")
        self.rule_index = rule_index
        self.rule_text = rule_text
        self.rule_view = view

    async def callback(self, interaction: discord.Interaction):
        view_obj = self.view
        if not isinstance(view_obj, RuleAcceptanceView):
            await interaction.response.send_message("⚠️ Invalid view state.", ephemeral=True)
            return
        if interaction.user.id != view_obj.member.id:
            await interaction.response.send_message("🚫 You cannot interact with this!", ephemeral=True)
            return

        view_obj.accepted_rules.add(self.rule_index)
        view_obj.current_rule += 1
        view_obj.update_buttons()
        if view_obj.current_rule < len(view_obj.rules):
            next_rule_text, next_rule_desc = view_obj.rules[view_obj.current_rule]
            embed = discord.Embed(
                title=next_rule_text,
                description=next_rule_desc,
                color=discord.Color.green()
            )
            embed.set_footer(text="Continue to the next rule.")
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1263189905555849317/1336037428049477724/Alpha_afbeelding_vierkant.png")
            await interaction.response.edit_message(embed=embed, view=view_obj)
        else:
            view_obj.clear_items()
            view_obj.add_item(FinalAcceptButton())
            await interaction.response.edit_message(view=view_obj)

class FinalAcceptButton(discord.ui.Button):
    """Knop waarmee een gebruiker aangeeft alle regels te accepteren en onboarding start."""
    def __init__(self):
        super().__init__(label="✅ Accept All Rules & Start Onboarding", style=discord.ButtonStyle.success, custom_id="final_accept")

    async def callback(self, interaction: discord.Interaction):
        view_obj = self.view
        if not isinstance(view_obj, RuleAcceptanceView):
            await interaction.response.send_message("⚠️ Invalid view state.", ephemeral=True)
            return
        if interaction.user.id != view_obj.member.id:
            await interaction.response.send_message("🚫 You cannot interact with this!", ephemeral=True)
            return
        
        if len(view_obj.accepted_rules) < len(view_obj.rules):
            await interaction.response.send_message("⚠️ You must accept all rules before proceeding!", ephemeral=True)
            return
    
        from cogs.onboarding import Onboarding
        bot_client = interaction.client
        onboarding_cog = getattr(bot_client, "get_cog", lambda name: None)("Onboarding")
        if onboarding_cog:
            print("✅ Onboarding Cog gevonden! Start onboarding...")
            await interaction.response.defer()
            await interaction.followup.send("✅ All rules accepted! Starting onboarding...", ephemeral=True)
            await onboarding_cog.send_next_question(interaction)
        else:
            print("❌ Onboarding Cog niet gevonden! Controleer of de onboarding module correct is geladen en actief is!")

class ReactionRole(commands.Cog):
    """Regelsysteem dat onboarding start via een knop in #rules."""
    def __init__(self, bot):
        self.bot = bot
        # Registreer de persistent view voor de start-knop
        self.bot.add_view(StartOnboardingView())

    @commands.Cog.listener()
    async def on_ready(self):
        """Plaats de onboarding-knop in #rules zodra de bot opstart (indien nog niet aanwezig)."""
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            print(f"⚠️ Guild {config.GUILD_ID} niet gevonden. Sla plaatsen onboarding-knop over.")
            return
        channel = guild.get_channel(config.RULES_CHANNEL_ID)
        if not channel:
            print(f"⚠️ Kanaal {config.RULES_CHANNEL_ID} niet gevonden in guild {guild.name}.")
            return

        # Helper: check of een bericht de Start Onboarding-knop bevat via custom_id
        def has_start_button(message: discord.Message) -> bool:
            try:
                for row in getattr(message, "components", []) or []:
                    # ActionRow kan 'children' (discord.py UI) of 'components' (API representatie) hebben
                    children = getattr(row, "children", None) or getattr(row, "components", [])
                    for comp in children:
                        if getattr(comp, "custom_id", None) == "start_onboarding":
                            return True
                return False
            except Exception:
                return False

        # Controleer of er al een bericht met de onboarding-knop staat op basis van custom_id
        try:
            messages = [message async for message in channel.history(limit=100)]
        except Exception as e:
            print(f"⚠️ Kon channel history niet lezen: {e}")
            return
        persistent_message = None
        for msg in messages:
            if has_start_button(msg):
                persistent_message = msg
                break

        if not persistent_message:
            embed = discord.Embed(
                title="Welcome to Alphapips™",
                description="The place where your learning and growth journey begins! 🌟\n\nTo get started, complete the verification by clicking the button below:",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1263189905555849317/1336037428049477724/Alpha_afbeelding_vierkant.png")
            await channel.send(embed=embed, view=StartOnboardingView())
            print("✅ Onboarding-knop geplaatst in #rules!")
        else:
            print("✅ Persistent onboarding message gevonden; geen duplicate verstuurd.")

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))
