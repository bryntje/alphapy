import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import logger
from config import LOG_CHANNEL_ID
from gpt.helpers import ask_gpt, log_gpt_success, log_gpt_error

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
        prompt = f"""
                You're a Discord community leadership coach.
                The leader struggles with: {struggle}.
                Respond with a brief reflection and a practical suggestion.
                Use a supportive, direct tone.
                """
        try:
            logger.info(f"GPT request by {interaction.user} — challenge: {struggle}")
            await interaction.response.defer(ephemeral=True)
            reply = await ask_gpt([{"role": "user", "content": prompt}])
            log_gpt_success(user_id=interaction.user.id)
            await interaction.followup.send(reply, ephemeral=True)
        except Exception as e:
            logger.exception(f"Unhandled GPT error (ChallengeSelect) by {interaction.user}: {e}")
            log_gpt_error("challenge_select", user_id=interaction.user.id)
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
        
            prompt = f"""
        You're a supportive leadership coach. A Discord leader asked:
        {user_question}
        Respond with clarity, honesty, and a helpful suggestion. Keep it short.
        """
        
            await interaction.followup.send("🧠 Thinking...", ephemeral=True)
        
            # ✅ En hier: gewoon rechtstreeks de prompt meesturen
            reply = await ask_gpt(
                [{"role": "user", "content": prompt}],
                user_id=interaction.user.id
            )
        
            log_gpt_success(user_id=interaction.user.id)
            await interaction.followup.send(reply, ephemeral=True)
        
        except Exception as e:
            logger.exception(f"Unhandled GPT error (AskQuestionButton) by {interaction.user}: {e}")
            log_gpt_error("ask_question", user_id=interaction.user.id)
            await interaction.followup.send("❌ Error occurred. Try again later.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LeaderHelp(bot))
