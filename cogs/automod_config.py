"""
Auto-Moderation Configuration Commands

Provides slash commands for configuring auto-mod rules and settings.
"""

import logging
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands
import asyncpg

from utils.premium_guard import guild_has_premium, is_premium
from utils.db_helpers import acquire_safe
from utils.logger import log_with_guild, logger
from utils.validators import validate_admin
from utils.automod_rules import RuleProcessor, RuleType, ActionType

logger = logging.getLogger(__name__)


class AutoModConfig(commands.Cog):
    """Configuration commands for auto-moderation system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rule_processor = RuleProcessor(bot)
        
    @staticmethod
    def requires_admin():
        """Check decorator for admin permissions."""
        async def predicate(interaction: discord.Interaction) -> bool:
            is_admin, _ = await validate_admin(interaction, raise_on_fail=False)
            if is_admin:
                return True
            raise app_commands.CheckFailure("You need administrator permissions for this command.")
        return app_commands.check(predicate)
        
    automod_group = app_commands.Group(
        name="automod",
        description="Manage auto-moderation settings",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @automod_group.command(name="create_rule", description="Create a new auto-mod rule")
    @app_commands.describe(
        rule_type="Type of rule (spam, content, regex)",
        name="Name for this rule",
        action_type="Action to take when rule is triggered"
    )
    @requires_admin()
    async def create_rule(self, interaction: discord.Interaction, rule_type: str, 
                         name: str, action_type: str):
        """Create a new auto-mod rule with interactive configuration."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Validate rule type
        valid_types = [t.value for t in RuleType]
        if rule_type not in valid_types:
            await interaction.response.send_message(
                f"❌ Invalid rule type. Valid types: {', '.join(valid_types)}",
                ephemeral=True
            )
            return
            
        # Validate action type
        valid_actions = [a.value for a in ActionType]
        if action_type not in valid_actions:
            await interaction.response.send_message(
                f"❌ Invalid action type. Valid types: {', '.join(valid_actions)}",
                ephemeral=True
            )
            return
            
        # Check premium requirements
        is_premium_feature = rule_type in ['ai', 'regex'] or action_type in ['timeout', 'ban']
        if is_premium_feature and not await guild_has_premium(guild_id):
            await interaction.response.send_message(
                "❌ This feature requires premium. Upgrade to unlock advanced auto-mod features.",
                ephemeral=True
            )
            return
            
        await interaction.response.send_message(
            "📝 Let's configure your rule step by step...",
            ephemeral=True
        )
        
        # Start interactive configuration
        await self._configure_rule_interactive(interaction, rule_type, name, action_type)
        
    async def _configure_rule_interactive(self, interaction: discord.Interaction, 
                                        rule_type: str, name: str, action_type: str):
        """Interactive rule configuration process."""
        if not interaction.guild:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        try:
            config = await self._get_rule_config(interaction, rule_type)
            if config is None:
                return  # User cancelled
                
            action_config = await self._get_action_config(interaction, action_type)
            if action_config is None:
                return  # User cancelled
                
            # Create the rule
            rule_id = await self.rule_processor.create_rule(
                guild_id=guild_id,
                rule_type=rule_type,
                name=name,
                config=config,
                action_type=action_type,
                action_config=action_config,
                created_by=interaction.user.id,
                is_premium=rule_type in ['ai', 'regex'] or action_type in ['timeout', 'ban']
            )
            
            await interaction.followup.send(
                f"✅ Rule '{name}' created successfully! (ID: {rule_id})",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error creating auto-mod rule: {e}")
            await interaction.followup.send(
                "❌ Error creating rule. Please try again.",
                ephemeral=True
            )
            
    async def _get_rule_config(self, interaction: discord.Interaction, rule_type: str) -> Optional[dict]:
        """Get configuration for a specific rule type."""
        if rule_type == RuleType.SPAM.value:
            return await self._configure_spam_rule(interaction)
        elif rule_type == RuleType.CONTENT.value:
            return await self._configure_content_rule(interaction)
        elif rule_type == RuleType.REGEX.value:
            return await self._configure_regex_rule(interaction)
        elif rule_type == RuleType.AI.value:
            return await self._configure_ai_rule(interaction)
        return {}
        
    async def _configure_spam_rule(self, interaction: discord.Interaction) -> Optional[dict]:
        """Configure spam detection rule."""
        view = SpamRuleView()
        await interaction.followup.send(
            "🚀 **Spam Rule Configuration**\n\n"
            "Choose the type of spam detection:",
            view=view,
            ephemeral=True
        )
        
        await view.wait()
        if not view.value:
            return None
            
        spam_type = view.value
        
        if spam_type == 'frequency':
            view2 = SpamFrequencyView()
            await interaction.followup.send(
                "⚡ **Frequency Spam Settings**\n\n"
                "Configure message frequency limits:",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            return {
                'spam_type': 'frequency',
                'max_messages': view2.value['max_messages'],
                'time_window': view2.value['time_window']
            }
            
        elif spam_type == 'duplicate':
            view2 = SpamDuplicateView()
            await interaction.followup.send(
                "🔄 **Duplicate Spam Settings**\n\n"
                "Configure duplicate message detection:",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            return {
                'spam_type': 'duplicate',
                'max_duplicates': view2.value['max_duplicates']
            }
            
        elif spam_type == 'caps':
            view2 = SpamCapsView()
            await interaction.followup.send(
                "📢 **Excessive Caps Settings**\n\n"
                "Configure caps usage limits:",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            return {
                'spam_type': 'caps',
                'min_length': view2.value['min_length'],
                'max_caps_ratio': view2.value['max_caps_ratio']
            }
            
        return None
        
    async def _configure_content_rule(self, interaction: discord.Interaction) -> Optional[dict]:
        """Configure content filtering rule."""
        view = ContentRuleView()
        await interaction.followup.send(
            "🔍 **Content Rule Configuration**\n\n"
            "Choose the type of content to filter:",
            view=view,
            ephemeral=True
        )
        
        await view.wait()
        if not view.value:
            return None
            
        content_type = view.value
        
        if content_type == 'bad_words':
            view2 = BadWordsView()
            await interaction.followup.send(
                "🚫 **Bad Words Filter**\n\n"
                "Enter words to filter (comma-separated):",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            return {
                'content_type': 'bad_words',
                'words': [word.strip() for word in view2.value['words'].split(',') if word.strip()]
            }
            
        elif content_type == 'links':
            view2 = LinksView()
            await interaction.followup.send(
                "🔗 **Link Filter Settings**\n\n"
                "Configure link filtering:",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            config = {
                'content_type': 'links',
                'allow_links': view2.value['allow_links']
            }
            
            if view2.value['whitelist']:
                config['whitelist'] = [site.strip() for site in view2.value['whitelist'].split(',')]
            if view2.value['blacklist']:
                config['blacklist'] = [site.strip() for site in view2.value['blacklist'].split(',')]
                
            return config
            
        elif content_type == 'mentions':
            view2 = MentionsView()
            await interaction.followup.send(
                "🏷️ **Mention Spam Settings**\n\n"
            "Configure mention limits:",
                view=view2,
                ephemeral=True
            )
            
            await view2.wait()
            if not view2.value:
                return None
                
            return {
                'content_type': 'mentions',
                'max_mentions': view2.value['max_mentions']
            }
            
        return None
        
    async def _configure_regex_rule(self, interaction: discord.Interaction) -> Optional[dict]:
        """Configure regex pattern rule."""
        view = RegexRuleView()
        await interaction.followup.send(
            "🎯 **Regex Rule Configuration**\n\n"
            "Enter regex patterns to match (one per line):",
            view=view,
            ephemeral=True
        )
        
        await view.wait()
        if not view.value:
            return None
            
        patterns = [pattern.strip() for pattern in view.value.split('\n') if pattern.strip()]
        
        return {
            'patterns': patterns
        }
        
    async def _configure_ai_rule(self, interaction: discord.Interaction) -> Optional[dict]:
        """Configure AI-powered rule."""
        view = AIRuleView()
        await interaction.followup.send(
            "🤖 **AI Rule Configuration**\n\n"
            "This feature uses advanced AI to detect inappropriate content.\n"
            "Configure the detection sensitivity:",
            view=view,
            ephemeral=True
        )
        
        await view.wait()
        if not view.value:
            return None
            
        return {
            'sensitivity': view.value['sensitivity'],
            'categories': view.value['categories']
        }
        
    async def _get_action_config(self, interaction: discord.Interaction, action_type: str) -> Optional[dict]:
        """Get configuration for a specific action type."""
        if action_type == ActionType.DELETE.value:
            return {}
        elif action_type == ActionType.WARN.value:
            view = WarnActionView()
            await interaction.followup.send(
                "⚠️ **Warning Action Configuration**\n\n"
                "Configure the warning message:",
                view=view,
                ephemeral=True
            )
            
            await view.wait()
            return {'message': view.value} if view.value else None
            
        elif action_type == ActionType.MUTE.value:
            view = MuteActionView()
            await interaction.followup.send(
                "🔇 **Mute Action Configuration**\n\n"
                "Select the mute role:",
                view=view,
                ephemeral=True
            )
            
            await view.wait()
            return {'mute_role_id': view.value} if view.value else None
            
        elif action_type == ActionType.TIMEOUT.value:
            view = TimeoutActionView()
            await interaction.followup.send(
                "⏰ **Timeout Action Configuration**\n\n"
                "Set the timeout duration:",
                view=view,
                ephemeral=True
            )
            
            await view.wait()
            return {'duration_minutes': view.value} if view.value else None
            
        return {}


# UI Components for Interactive Configuration
class SpamRuleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="📊 Frequency", style=discord.ButtonStyle.primary)
    async def frequency(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'frequency'
        await interaction.response.edit_message(content="✅ Frequency spam selected", view=None)
        self.stop()
        
    @discord.ui.button(label="🔄 Duplicates", style=discord.ButtonStyle.primary)
    async def duplicates(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'duplicate'
        await interaction.response.edit_message(content="✅ Duplicate spam selected", view=None)
        self.stop()
        
    @discord.ui.button(label="📢 Excessive Caps", style=discord.ButtonStyle.primary)
    async def caps(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'caps'
        await interaction.response.edit_message(content="✅ Excessive caps selected", view=None)
        self.stop()


class SpamFrequencyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="5 msgs / 60s", style=discord.ButtonStyle.primary)
    async def low(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'max_messages': 5, 'time_window': 60}
        await interaction.response.edit_message(content="✅ Low sensitivity selected", view=None)
        self.stop()
        
    @discord.ui.button(label="10 msgs / 60s", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'max_messages': 10, 'time_window': 60}
        await interaction.response.edit_message(content="✅ Medium sensitivity selected", view=None)
        self.stop()
        
    @discord.ui.button(label="15 msgs / 60s", style=discord.ButtonStyle.primary)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'max_messages': 15, 'time_window': 60}
        await interaction.response.edit_message(content="✅ High sensitivity selected", view=None)
        self.stop()


class SpamDuplicateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="2 duplicates", style=discord.ButtonStyle.primary)
    async def low(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 2
        await interaction.response.edit_message(content="✅ Strict duplicate detection", view=None)
        self.stop()
        
    @discord.ui.button(label="3 duplicates", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 3
        await interaction.response.edit_message(content="✅ Medium duplicate detection", view=None)
        self.stop()
        
    @discord.ui.button(label="5 duplicates", style=discord.ButtonStyle.primary)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 5
        await interaction.response.edit_message(content="✅ Lenient duplicate detection", view=None)
        self.stop()


class SpamCapsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="70% caps", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'min_length': 10, 'max_caps_ratio': 0.7}
        await interaction.response.edit_message(content="✅ Medium caps detection", view=None)
        self.stop()
        
    @discord.ui.button(label="80% caps", style=discord.ButtonStyle.primary)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'min_length': 10, 'max_caps_ratio': 0.8}
        await interaction.response.edit_message(content="✅ High caps detection", view=None)
        self.stop()


class ContentRuleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="🚫 Bad Words", style=discord.ButtonStyle.primary)
    async def bad_words(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'bad_words'
        await interaction.response.edit_message(content="✅ Bad words filter selected", view=None)
        self.stop()
        
    @discord.ui.button(label="🔗 Links", style=discord.ButtonStyle.primary)
    async def links(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'links'
        await interaction.response.edit_message(content="✅ Link filter selected", view=None)
        self.stop()
        
    @discord.ui.button(label="🏷️ Mentions", style=discord.ButtonStyle.primary)
    async def mentions(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'mentions'
        await interaction.response.edit_message(content="✅ Mention spam selected", view=None)
        self.stop()


class BadWordsView(discord.ui.Modal, title="Bad Words Configuration"):
    def __init__(self):
        super().__init__()
        self.words = discord.ui.TextInput(
            label="Words to filter (comma-separated)",
            placeholder="badword1, badword2, badword3",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.words)
        
    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.words.value
        await interaction.response.send_message("✅ Bad words configured", ephemeral=True)


class LinksView(discord.ui.Modal, title="Link Filter Configuration"):
    def __init__(self):
        super().__init__()
        self.allow_links = discord.ui.TextInput(
            label="Allow links? (yes/no)",
            placeholder="no",
            style=discord.TextStyle.short,
            required=True
        )
        self.whitelist = discord.ui.TextInput(
            label="Whitelisted domains (comma-separated)",
            placeholder="youtube.com, twitch.tv",
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.blacklist = discord.ui.TextInput(
            label="Blacklisted domains (comma-separated)",
            placeholder="spam.com, malware.net",
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.add_item(self.allow_links)
        self.add_item(self.whitelist)
        self.add_item(self.blacklist)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.value = {
            'allow_links': self.allow_links.value.lower() == 'yes',
            'whitelist': self.whitelist.value,
            'blacklist': self.blacklist.value
        }
        await interaction.response.send_message("✅ Link filter configured", ephemeral=True)


class MentionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="3 mentions", style=discord.ButtonStyle.primary)
    async def low(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 3
        await interaction.response.edit_message(content="✅ Low mention limit", view=None)
        self.stop()
        
    @discord.ui.button(label="5 mentions", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 5
        await interaction.response.edit_message(content="✅ Medium mention limit", view=None)
        self.stop()
        
    @discord.ui.button(label="10 mentions", style=discord.ButtonStyle.primary)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 10
        await interaction.response.edit_message(content="✅ High mention limit", view=None)
        self.stop()


class RegexRuleView(discord.ui.Modal, title="Regex Pattern Configuration"):
    def __init__(self):
        super().__init__()
        self.patterns = discord.ui.TextInput(
            label="Regex patterns (one per line)",
            placeholder="(?i).*spam.*\n(?i).*scam.*",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.patterns)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.patterns.value
        await interaction.response.send_message("✅ Regex patterns configured", ephemeral=True)


class AIRuleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="🔍 Low Sensitivity", style=discord.ButtonStyle.primary)
    async def low(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'sensitivity': 'low', 'categories': ['toxicity', 'spam']}
        await interaction.response.edit_message(content="✅ Low sensitivity AI detection", view=None)
        self.stop()
        
    @discord.ui.button(label="⚖️ Medium Sensitivity", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'sensitivity': 'medium', 'categories': ['toxicity', 'spam', 'harassment']}
        await interaction.response.edit_message(content="✅ Medium sensitivity AI detection", view=None)
        self.stop()
        
    @discord.ui.button(label="🚨 High Sensitivity", style=discord.ButtonStyle.primary)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = {'sensitivity': 'high', 'categories': ['toxicity', 'spam', 'harassment', 'threats']}
        await interaction.response.edit_message(content="✅ High sensitivity AI detection", view=None)
        self.stop()


class WarnActionView(discord.ui.Modal, title="Warning Message Configuration"):
    def __init__(self):
        super().__init__()
        self.message = discord.ui.TextInput(
            label="Warning message",
            placeholder="⚠️ Your message violates server rules.",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.message)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.message.value
        await interaction.response.send_message("✅ Warning message configured", ephemeral=True)


class MuteActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.select(
        placeholder="Select mute role",
        min_values=1,
        max_values=1
    )
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.value = int(select.values[0])
        await interaction.response.edit_message(content=f"✅ Mute role selected", view=None)
        self.stop()
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Populate roles with "Muted" in name
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild not found.", ephemeral=True)
            return False
            
        roles = [role for role in interaction.guild.roles if "muted" in role.name.lower()]
        if not roles:
            await interaction.response.send_message(
                "❌ No muted roles found. Please create a role with 'Muted' in the name first.",
                ephemeral=True
            )
            return False
            
        self.select_role.options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles[:25]  # Discord limit
        ]
        return True


class TimeoutActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
        
    @discord.ui.button(label="5 minutes", style=discord.ButtonStyle.primary)
    async def short(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 5
        await interaction.response.edit_message(content="✅ 5 minute timeout", view=None)
        self.stop()
        
    @discord.ui.button(label="15 minutes", style=discord.ButtonStyle.primary)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 15
        await interaction.response.edit_message(content="✅ 15 minute timeout", view=None)
        self.stop()
        
    @discord.ui.button(label="1 hour", style=discord.ButtonStyle.primary)
    async def long(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 60
        await interaction.response.edit_message(content="✅ 1 hour timeout", view=None)
        self.stop()


async def setup(bot: commands.Bot):
    """Setup the AutoModConfig cog."""
    await bot.add_cog(AutoModConfig(bot))
