import discord
from discord.ext import commands
import config
from utils.logger import log_with_guild

class StartOnboardingView(discord.ui.View):
    """View with a button to start onboarding directly."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartOnboardingButton())

class StartOnboardingButton(discord.ui.Button):
    """Button to accept rules and start onboarding directly."""
    def __init__(self):
        # Use a fixed custom_id so this is recognized as a persistent view.
        super().__init__(label="🚀 Start Onboarding", style=discord.ButtonStyle.success, custom_id="start_onboarding")
        
    async def callback(self, interaction: discord.Interaction):
        member = interaction.user

        # Check onboarding settings
        enabled = interaction.client.settings.get("onboarding", "enabled", interaction.guild.id)
        mode = interaction.client.settings.get("onboarding", "mode", interaction.guild.id)

        if not enabled or mode == "disabled":
            await interaction.response.send_message("🚫 Onboarding is currently disabled.", ephemeral=True)
            return

        # Handle different modes
        if mode == "questions_only":
            # Skip rules, go directly to questions
            from cogs.onboarding import Onboarding
            onboarding_cog = getattr(interaction.client, "get_cog", lambda name: None)("Onboarding")
            if onboarding_cog:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("📝 Starting onboarding questions...", ephemeral=True)
                await onboarding_cog.send_next_question(interaction)
            else:
                await interaction.response.send_message("❌ Onboarding system unavailable.", ephemeral=True)

        elif mode in ["rules_only", "rules_with_questions"]:
            # Start with the rules
            rules_view = RuleAcceptanceView(member, interaction.guild.id)
            await rules_view.load_rules(interaction.client)
            await interaction.response.send_message(
                "📜 Please accept each rule one by one before proceeding:",
                view=rules_view,
                ephemeral=True  # Keep the message private
            )

        else:
            await interaction.response.send_message("🚫 Unknown onboarding mode.", ephemeral=True)

class RuleAcceptanceView(discord.ui.View):
    """View where users must accept rules one by one before proceeding to onboarding."""
    def __init__(self, member, guild_id: int):
        super().__init__(timeout=None)
        self.member = member
        self.guild_id = guild_id
        self.current_rule = 0
        self.accepted_rules = set()
        self.rules = []  # Will be loaded asynchronously
        # Don't call update_buttons() here - it will be called after rules are loaded

    async def load_rules(self, bot):
        """Load rules for this guild."""
        onboarding_cog = bot.get_cog("Onboarding")
        if onboarding_cog:
            self.rules = await onboarding_cog.get_guild_rules(self.guild_id)
        else:
            # Fallback to default rules if onboarding cog not available
            self.rules = [
                ("🛡️ Respect Others", "Stay constructive & professional."),
                ("🚫 No Spam or Promotions", "External links, ads, and spam are forbidden."),
                ("📚 Educational Content Only", "Share only educational content relevant to this community."),
                ("🌟 Community Guidelines", "Follow server-specific rules and guidelines."),
                ("💰 No Financial Advice", "This community provides education, not financial advice.")
            ]
        self.update_buttons()

    def update_buttons(self):
        """Update the buttons so only the current rule is shown."""
        self.clear_items()
        if self.current_rule < len(self.rules):
            rule_text, _ = self.rules[self.current_rule]
            self.add_item(RuleButton(rule_index=self.current_rule, rule_text=rule_text, view=self))
        elif len(self.accepted_rules) == len(self.rules):
            self.add_item(FinalAcceptButton())

class RuleButton(discord.ui.Button):
    """Button to accept a rule."""
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
    """Button where user indicates they accept all rules and onboarding starts."""
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

        # Check onboarding settings
        bot_client = interaction.client
        enabled = bot_client.settings.get("onboarding", "enabled", interaction.guild.id)
        mode = bot_client.settings.get("onboarding", "mode", interaction.guild.id)
        completion_role_id = bot_client.settings.get("onboarding", "completion_role_id", interaction.guild.id)

        if not enabled or mode == "disabled":
            await interaction.response.send_message("✅ Rules accepted! Welcome to the server.", ephemeral=True)
            return

        # Assign completion role if set
        assigned_role = False
        if completion_role_id and completion_role_id != 0:
            try:
                role = interaction.guild.get_role(completion_role_id)
                if role:
                    await view_obj.member.add_roles(role)
                    assigned_role = True
                    print(f"✅ Role {role.name} assigned to {view_obj.member.display_name}")
            except Exception as e:
                print(f"⚠️ Could not assign role: {e}")

        # Handle different onboarding modes
        if mode == "rules_only":
            message = "✅ Rules accepted!"
            if assigned_role:
                message += f" You have been assigned the {role.mention} role." if 'role' in locals() else " You have been assigned a role."
            message += " Welcome to the server!"
            await interaction.response.send_message(message, ephemeral=True)

        elif mode in ["rules_with_questions", "questions_only"]:
            from cogs.onboarding import Onboarding
            onboarding_cog = getattr(bot_client, "get_cog", lambda name: None)("Onboarding")
            if onboarding_cog:
                print("✅ Onboarding Cog found! Starting onboarding...")
                await interaction.response.defer()
                message = "✅ Rules accepted!"
                if assigned_role:
                    message += f" You have been assigned the {role.mention} role." if 'role' in locals() else " You have been assigned a role."
                message += " Starting onboarding questions..."
                await interaction.followup.send(message, ephemeral=True)
                await onboarding_cog.send_next_question(interaction)
            else:
                print("❌ Onboarding Cog not found! Check if the onboarding module is loaded and active!")
                await interaction.response.send_message("✅ Rules accepted! Welcome to the server.", ephemeral=True)

        else:
            await interaction.response.send_message("✅ Rules accepted! Welcome to the server.", ephemeral=True)

class ReactionRole(commands.Cog):
    """Rule system that starts onboarding via a button in #rules."""
    def __init__(self, bot):
        self.bot = bot
        # Register the persistent view for the start button
        self.bot.add_view(StartOnboardingView())

    @commands.Cog.listener()
    async def on_ready(self):
        """Place the onboarding button in #rules for all guilds the bot is in."""
        for guild in self.bot.guilds:
            # Get rules channel from settings for this guild
            try:
                rules_channel_id = int(self.bot.settings.get("system", "rules_channel_id", guild.id))
                if rules_channel_id == 0:
                    # No channel configured for this guild
                    log_with_guild(f"No rules channel configured for guild {guild.name}", guild.id, "debug")
                    continue
                channel = guild.get_channel(rules_channel_id)
                if not channel:
                    log_with_guild(f"Rules channel {rules_channel_id} not found in guild {guild.name}", guild.id, "warning")
                    continue
            except (KeyError, ValueError):
                # No channel configured, skip
                log_with_guild(f"No rules channel set for guild {guild.name}", guild.id, "debug")
                continue

            # Helper: check if a message contains the Start Onboarding button via custom_id
            def has_start_button(message: discord.Message) -> bool:
                try:
                    for row in getattr(message, "components", []) or []:
                        # ActionRow can have 'children' (discord.py UI) or 'components' (API representation)
                        children = getattr(row, "children", None) or getattr(row, "components", [])
                        for comp in children:
                            if getattr(comp, "custom_id", None) == "start_onboarding":
                                return True
                    return False
                except Exception:
                    return False

            # Check if there's already a message with the onboarding button based on custom_id
            try:
                messages = [message async for message in channel.history(limit=100)]
            except Exception as e:
                print(f"⚠️ Could not read channel history in guild {guild.name}: {e}")
                continue

            persistent_message = None
            for msg in messages:
                if has_start_button(msg):
                    persistent_message = msg
                    break

            if not persistent_message:
                embed = discord.Embed(
                    title=f"Welcome to {guild.name}",
                    description="The place where your learning and growth journey begins! 🌟\n\nTo get started, complete the verification by clicking the button below:",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1263189905555849317/1336037428049477724/Alpha_afbeelding_vierkant.png")
                try:
                    await channel.send(embed=embed, view=StartOnboardingView())
                    print(f"✅ Onboarding button placed in #{channel.name} for guild {guild.name}!")
                except Exception as e:
                    print(f"⚠️ Could not place onboarding button in guild {guild.name}: {e}")
            else:
                print(f"✅ Persistent onboarding message found for guild {guild.name}; no duplicate sent.")

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))
