"""
Test Auto-Moderation Implementation

Basic test script to verify auto-mod functionality.
"""

import asyncio
import logging
from typing import Dict, Any

import discord
from discord.ext import commands

from utils.automod_rules import RuleProcessor, RuleType, ActionType, RuleResult
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
        result = await self.rule_processor.evaluate_rule(rule, mock_message, user_context)
        
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
        result = await self.rule_processor.evaluate_rule(rule, mock_message, {})
        
        if result.triggered:
            await ctx.send(f"✅ Bad words detected: {result.reason}")
        else:
            await ctx.send("❌ Bad words not detected (expected detection)")
            
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


async def setup(bot: commands.Bot):
    """Setup the test auto-mod cog."""
    await bot.add_cog(TestAutoMod(bot))
