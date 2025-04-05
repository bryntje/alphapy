import discord
from discord.ext import commands
from discord import app_commands
from openai import AsyncOpenAI, RateLimitError
from logger import logger
from config import LOG_CHANNEL_ID
from gptstatus import log_gpt_success, log_gpt_error
import config

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

class LeaderHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="leaderhelp",
        description="Get AI-powered leadership guidance for challenges, team growth, or doubts."
    )
    async def leaderhelp(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What kind of support do you want?",
            ephemeral=True,
            view=LeaderOptions(self.bot)
        )

class LeaderOptions(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=90)
        self.bot = bot

        self.add_item(ChallengeSelect(bot))
        self.add_item(AskQuestionButton(bot))

class ChallengeSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="My team is disengaged", value="disengaged"),
            discord.SelectOption(label="Leadership feels exhausting", value="burnout"),
            discord.SelectOption(label="People are dropping off", value="dropoff"),
            discord.SelectOption(label="I’m doubting myself", value="self_doubt")
        ]
        super().__init__(placeholder="Choose a challenge...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        struggle = self.values[0]
        prompt = f"""You're a Discord community leadership coach.
                    The leader struggles with: {struggle}.
                    Respond with a brief reflection and a practical suggestion.
                    Use a supportive, direct tone."""

        try:
            logger.info(f"GPT request by {interaction.user} — challenge: {struggle}")

            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600
            )

            content = response.choices[0].message.content
            logger.info(f"GPT response: {content[:100]}...")  # truncate log
            log_gpt_success()
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(content, ephemeral=True)

        except RateLimitError as e:
            logger.warning(f"Rate limit hit by {interaction.user}: {e}")
            log_gpt_error("rate_limit")
            await interaction.followup.send("⚠️ Too many requests to OpenAI. Try again shortly.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Unhandled GPT error (ChallengeSelect) by {interaction.user}: {e}")
            log_gpt_error("general")
            await interaction.followup.send("❌ Something went wrong. Please try again later.", ephemeral=True)

class AskQuestionButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Ask your own question", style=discord.ButtonStyle.primary)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Please type your leadership question (any language):", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", timeout=120.0, check=check)
            user_question = msg.content.strip()

            logger.info(f"{interaction.user} asked: {user_question[:100]}")

            prompt = f"""You're a supportive leadership coach. A Discord leader asked:
                {user_question}
                Respond with clarity, honesty, and a helpful suggestion. Keep it short."""

            await interaction.followup.send("🧠 Thinking...", ephemeral=True)

            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600
            )

            content = response.choices[0].message.content
            logger.info(f"GPT response: {content[:100]}...")  # truncate
            log_gpt_success()
            await interaction.followup.send(content, ephemeral=True)

        except RateLimitError as e:
            logger.warning(f"Rate limit (ask custom) by {interaction.user}: {e}")
            await interaction.followup.send("⚠️ Too many requests to OpenAI. Try again soon.", ephemeral=True)
            await log_to_discord(self.bot, "warn", f"Rate limit hit by {interaction.user}")
            log_gpt_error("rate_limit")


        except Exception as e:
            logger.exception(f"Unhandled GPT error (AskQuestionButton) by {interaction.user}: {e}")
            log_gpt_error("general")
            await interaction.followup.send("❌ Error occurred. Try again later.", ephemeral=True)


async def log_to_discord(bot, level: str, text: str):
    """Send GPT system-level info to logs channel"""
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            logger.warning("Discord log channel not found.")
            return

        emoji = {
            "info": "ℹ️",
            "warn": "⚠️",
            "error": "❌"
        }.get(level, "📡")

        await channel.send(f"{emoji} {text}")

    except Exception as e:
        logger.error(f"Failed to send log to Discord: {e}")


async def setup(bot):
    await bot.add_cog(LeaderHelp(bot))
