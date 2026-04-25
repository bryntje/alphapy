"""
Test Auto-Moderation Implementation

Basic test script to verify auto-mod functionality.
"""

import logging
from typing import cast

import discord
from discord.ext import commands

from utils.automod_rules import RuleProcessor
from utils.logger import logger

logger = logging.getLogger(__name__)


class MockMessage:
    """Mock message class for testing auto-mod rules."""
    def __init__(self, content: str, author: discord.User, channel: discord.TextChannel):
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = channel.guild
        self.id = 12345
        self.mentions = []
        
    # Add type compatibility methods to match discord.Message interface
    def __getattr__(self, name):
        # Return None for any missing attributes to avoid AttributeError
        return None


class TestAutoMod(commands.Cog):
    """Test commands for auto-moderation system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rule_processor = RuleProcessor(bot)
        
    @commands.command(name="testautomod")
    @commands.is_owner()
    async def test_automod(self, ctx):
        """Test auto-mod rule processing."""
        await ctx.send("🧪 Testing auto-mod system...")
        
        # Test spam detection
        await self._test_spam_detection(ctx)
        
        # Test content filtering
        await self._test_content_filtering(ctx)

        # Test additional rule evaluators
        await self._test_link_filtering(ctx)
        await self._test_mention_spam(ctx)
        await self._test_caps_spam(ctx)
        await self._test_duplicate_spam(ctx)
        
        await ctx.send("✅ Auto-mod tests completed!")
        
    async def _test_spam_detection(self, ctx):
        """Test spam detection rules."""
        await ctx.send("📊 Testing spam detection...")
        
        # Test frequency spam
        rule = {
            'id': 1,
            'rule_type': 'spam',
            'config': {
                'spam_type': 'frequency',
                'max_messages': 5,
                'time_window': 60
            }
        }
        
        user_context = {
            'message_timestamps': [1, 2, 3, 4, 5, 6],  # 6 messages
            'spam_count': 6
        }
        
        mock_message = MockMessage("test message", ctx.author, ctx.channel)
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), user_context)
        
        if result.triggered:
            await ctx.send(f"✅ Frequency spam detected: {result.reason}")
        else:
            await ctx.send("❌ Frequency spam not detected (expected detection)")
            
    async def _test_content_filtering(self, ctx):
        """Test content filtering rules."""
        await ctx.send("🔍 Testing content filtering...")
        
        # Test bad words
        rule = {
            'id': 2,
            'rule_type': 'content',
            'config': {
                'content_type': 'bad_words',
                'words': ['spam', 'scam']
            }
        }
        
        mock_message = MockMessage("This is spam content", ctx.author, ctx.channel)
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), {})
        
        if result.triggered:
            await ctx.send(f"✅ Bad words detected: {result.reason}")
        else:
            await ctx.send("❌ Bad words not detected (expected detection)")

    async def _test_link_filtering(self, ctx):
        """Test link filtering evaluator."""
        await ctx.send("🔗 Testing link filtering...")
        rule = {
            'id': 3,
            'rule_type': 'content',
            'config': {
                'content_type': 'links',
                'allow_links': False,
                'whitelist': [],
                'blacklist': []
            }
        }
        mock_message = MockMessage("Check this out https://spam.example.com", ctx.author, ctx.channel)
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), {})
        if result.triggered:
            await ctx.send(f"✅ Link filtering triggered: {result.reason}")
        else:
            await ctx.send("❌ Link filtering did not trigger (expected trigger)")

    async def _test_mention_spam(self, ctx):
        """Test mention spam evaluator."""
        await ctx.send("👥 Testing mention spam...")
        rule = {
            'id': 4,
            'rule_type': 'content',
            'config': {
                'content_type': 'mentions',
                'max_mentions': 2
            }
        }
        mock_message = MockMessage("Hey all", ctx.author, ctx.channel)
        mock_message.mentions = [ctx.author, ctx.author, ctx.author]
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), {})
        if result.triggered:
            await ctx.send(f"✅ Mention spam detected: {result.reason}")
        else:
            await ctx.send("❌ Mention spam not detected (expected detection)")

    async def _test_caps_spam(self, ctx):
        """Test caps spam evaluator."""
        await ctx.send("🔠 Testing caps spam...")
        rule = {
            'id': 5,
            'rule_type': 'spam',
            'config': {
                'spam_type': 'caps',
                'min_length': 10,
                'max_caps_ratio': 0.7
            }
        }
        mock_message = MockMessage("THIS MESSAGE IS FULL OF CAPS", ctx.author, ctx.channel)
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), {})
        if result.triggered:
            await ctx.send(f"✅ Caps spam detected: {result.reason}")
        else:
            await ctx.send("❌ Caps spam not detected (expected detection)")

    async def _test_duplicate_spam(self, ctx):
        """Test duplicate spam evaluator."""
        await ctx.send("♻️ Testing duplicate spam...")
        rule = {
            'id': 6,
            'rule_type': 'spam',
            'config': {
                'spam_type': 'duplicate',
                'max_duplicates': 3
            }
        }
        user_context = {
            'last_message': 'same text',
            'message_timestamps': [1, 2, 3, 4],
        }
        mock_message = MockMessage("same text", ctx.author, ctx.channel)
        result = await self.rule_processor.evaluate_rule(rule, cast(discord.Message, mock_message), user_context)
        if result.triggered:
            await ctx.send(f"✅ Duplicate spam detected: {result.reason}")
        else:
            await ctx.send("❌ Duplicate spam not detected (expected detection)")
            
    @commands.command(name="testautomodconfig")
    @commands.is_owner()
    async def test_automod_config(self, ctx):
        """Test auto-mod configuration creation."""
        await ctx.send("⚙️ Testing auto-mod configuration...")
        
        try:
            # This would require a database connection
            guild_id = ctx.guild.id
            
            # Test creating a simple spam rule
            rule_id = await self.rule_processor.create_rule(
                guild_id=guild_id,
                rule_type='spam',
                name='Test Spam Rule',
                config={
                    'spam_type': 'frequency',
                    'max_messages': 5,
                    'time_window': 60
                },
                action_type='warn',
                action_config={'message': '⚠️ Please avoid spamming.'},
                created_by=ctx.author.id,
                is_premium=False
            )
            
            await ctx.send(f"✅ Test rule created with ID: {rule_id}")
            
        except Exception as e:
            await ctx.send(f"❌ Error creating test rule: {e}")
            logger.error(f"Test auto-mod config error: {e}")

    @commands.command(name="testautomodcrud")
    @commands.is_owner()
    async def test_automod_crud(self, ctx):
        """Test auto-mod rule CRUD operations."""
        if not ctx.guild:
            await ctx.send("❌ This command only works in a server.")
            return

        await ctx.send("🗃️ Testing auto-mod CRUD...")
        guild_id = ctx.guild.id
        created_rule_id: int | None = None

        try:
            created_rule_id = await self.rule_processor.create_rule(
                guild_id=guild_id,
                rule_type='spam',
                name='CRUD Test Rule',
                config={
                    'spam_type': 'frequency',
                    'max_messages': 4,
                    'time_window': 30
                },
                action_type='warn',
                action_config={'message': 'Test warning'},
                created_by=ctx.author.id,
                is_premium=False
            )
            await ctx.send(f"✅ Created rule `{created_rule_id}`")

            rows = await self.rule_processor.list_rules(guild_id)
            if any(int(r.get("id", 0)) == created_rule_id for r in rows):
                await ctx.send("✅ List includes created rule")
            else:
                await ctx.send("❌ Created rule missing from list")

            updated = await self.rule_processor.update_rule(
                guild_id=guild_id,
                rule_id=created_rule_id,
                name="CRUD Test Rule Updated",
                enabled=False,
                action_type="delete",
            )
            await ctx.send("✅ Rule updated" if updated else "❌ Rule update failed")

            deleted = await self.rule_processor.delete_rule(guild_id, created_rule_id)
            await ctx.send("✅ Rule deleted" if deleted else "❌ Rule delete failed")
        except Exception as e:
            await ctx.send(f"❌ CRUD test failed: {e}")
            logger.error(f"Test auto-mod CRUD error: {e}")
            if created_rule_id:
                try:
                    await self.rule_processor.delete_rule(guild_id, created_rule_id)
                except Exception:
                    pass


async def setup(bot: commands.Bot):
    """Setup the test auto-mod cog."""
    await bot.add_cog(TestAutoMod(bot))
