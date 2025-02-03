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
        super().__init__(label="🚀 Start Onboarding", style=discord.ButtonStyle.success, custom_id="start_onboarding")

    async def callback(self, interaction: discord.Interaction):
        """Start onboarding proces zodra de knop wordt ingedrukt."""
        member = interaction.user
        
        # Start met de regels
        rules_view = RuleAcceptanceView(member)
        await interaction.response.send_message(
            "📜 Please accept each rule one by one before proceeding:",
            view=rules_view,
            ephemeral=True  # 🔥 Houd alles privé!
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
            self.add_item(RuleButton(rule_index=self.current_rule, view=self))
        else:
            self.add_item(FinalAcceptButton())

class RuleButton(discord.ui.Button):
    """Knop om een regel te accepteren."""
    
    def __init__(self, rule_index, view):
        rule_text, _ = view.rules[rule_index]
        super().__init__(label=f"✅ I Accept", style=discord.ButtonStyle.primary, custom_id=f"rule_{rule_index}")
        self.rule_index = rule_index

    async def callback(self, interaction: discord.Interaction):
        view: RuleAcceptanceView = self.view
        if interaction.user.id != view.member.id:
            await interaction.response.send_message("🚫 You cannot interact with this!", ephemeral=True)
            return
        
        rule_text, rule_desc = view.rules[self.rule_index]
        view.accepted_rules.add(self.rule_index)
        view.current_rule += 1
        view.update_buttons()

        embed = discord.Embed(
            title=rule_text,
            description=rule_desc,
            color=discord.Color.green()
        )
        embed.set_footer(text="Continue to the next rule.")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1263189905555849317/1336037428049477724/Alpha_afbeelding_vierkant.png")

        await interaction.response.edit_message(embed=embed, view=view)

class FinalAcceptButton(discord.ui.Button):
    """Knop om alle regels te accepteren en onboarding te starten."""
    
    def __init__(self):
        super().__init__(label="✅ Accept All Rules & Start Onboarding", style=discord.ButtonStyle.success, custom_id="accept_all")

    async def callback(self, interaction: discord.Interaction):
        view: RuleAcceptanceView = self.view
        if interaction.user.id != view.member.id:
            await interaction.response.send_message("🚫 You cannot interact with this!", ephemeral=True)
            return

        from onboarding import Onboarding

        onboarding_cog = interaction.client.get_cog("Onboarding")
        if onboarding_cog:
            print("✅ Onboarding Cog gevonden! Start onboarding...")
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("✅ All rules accepted! Starting onboarding...", ephemeral=True)
            await onboarding_cog.send_next_question(interaction)
        else:
            print("❌ Onboarding Cog niet gevonden! Controleer of de onboarding module correct is geladen en actief is!")

class ReactionRole(commands.Cog):
    """Regelsysteem dat onboarding start via een knop in #rules."""
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(StartOnboardingView())  # ✅ Registreer de View

    @commands.Cog.listener()
    async def on_ready(self):
        """Plaats de onboarding-knop in #rules zodra de bot opstart."""
        guild = self.bot.get_guild(config.GUILD_ID)
        channel = guild.get_channel(config.RULES_CHANNEL_ID)

        if channel:
            embed = discord.Embed(
                title="Welcome to Alphapips™",
                description="The place where your learning and growth journey begins! 🌟\n\nTo get started, complete the verification by clicking the button below:",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1263189905555849317/1336037428049477724/Alpha_afbeelding_vierkant.png")
            
            await channel.send(embed=embed, view=StartOnboardingView())
            print("✅ Onboarding-knop geplaatst in #rules!")



async def setup(bot):
    await bot.add_cog(ReactionRole(bot))
