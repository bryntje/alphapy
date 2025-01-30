import discord
from discord.ext import commands
import config

class RuleAcceptanceView(discord.ui.View):
    """View waarin gebruikers regels één voor één moeten accepteren voordat ze doorgaan naar onboarding."""

    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member
        self.current_rule = 0
        self.accepted_rules = set()
        self.rules = [
            ("Respect Others", "Stay constructive & professional."),
            ("No Spam or Promotions", "External links, ads, and spam are forbidden."),
            ("Educational Content Only", "Do not share content outside Alphapips™."),
            ("Ambassador Content Sharing", "Only approved ambassadors may share externally."),
            ("No Financial Advice", "Alphapips™ provides education, not financial advice.")
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

        await interaction.response.edit_message(
            content=f"**{rule_text} Accepted**\n*{rule_desc}*", view=view
        )

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
            for cog in interaction.client.cogs:
                print(f"🛠 Actieve cog: {cog}")  # ✅ Debug om te zien welke Cogs wél geladen zijn.



class ReactionRole(commands.Cog):
    """Regelsysteem dat onboarding start wanneer iemand op ✅ reageert in #rules."""
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(StartRulesView())  # ✅ Registreer de View

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        print(f"🔄 Reaction detected van user ID: {payload.user_id}, emoji: {payload.emoji.name}, channel ID: {payload.channel_id}")

        if payload.channel_id == config.RULES_CHANNEL_ID and payload.emoji.name == "✅":
                print("✅ Vinkje geregistreerd!")

                guild = self.bot.get_guild(config.GUILD_ID)
                if guild is None:
                    print("❌ Guild niet gevonden! Check config.GUILD_ID")
                    return

                print(f"🏰 Guild gevonden: {guild.name}")

                member = await guild.fetch_member(payload.user_id)
                if member is None or member.bot:
                    print("❌ Member niet gevonden of is een bot! User ID:", payload.user_id)
                    return

                print(f"👤 Member gevonden: {member.name}")

                onboarding_channel = guild.get_channel(config.ONBOARDING_CHANNEL_ID)
                if onboarding_channel:
                    print(f"📩 Stuur start message naar {onboarding_channel.name}")
                    await onboarding_channel.send(
                        f"{member.mention}, click the button below to start accepting the rules.",
                        view=StartRulesView()
                    )
                else:
                    print("❌ Onboarding channel niet gevonden! Check config.ONBOARDING_CHANNEL_ID")




@commands.command()
async def check_channels(ctx):
    rules_channel = ctx.bot.get_channel(config.RULES_CHANNEL_ID)
    if rules_channel:
        await ctx.send(f"✅ Rules channel gevonden: {rules_channel.name}")
    else:
        await ctx.send("❌ Rules channel niet gevonden! Controleer config.py.")

    onboarding_channel = ctx.bot.get_channel(config.ONBOARDING_CHANNEL_ID)
    if onboarding_channel:
        await ctx.send(f"✅ Onboarding channel gevonden: {onboarding_channel.name}")
    else:
        await ctx.send("❌ Onboarding channel niet gevonden! Controleer config.py.")



class StartRulesView(discord.ui.View):
    """View met een knop om de regel-acceptatie te starten."""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartRulesButton())

class StartRulesButton(discord.ui.Button):
    """Knop om de regel-acceptatie te starten."""
    
    def __init__(self):
        super().__init__(label="Start Rule Acceptance", style=discord.ButtonStyle.success, custom_id="start_rules")

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        view = RuleAcceptanceView(member)
        await interaction.response.send_message(
            "📝 Please accept each rule one by one before proceeding:",
            view=view,
            ephemeral=True  # 🔥 Nu wél ephemeral!
        )

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))
