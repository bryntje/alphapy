import discord
from discord.ext import commands
from discord import app_commands
from openai import AsyncOpenAI
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
        prompt = f"""I'm a community leader on Discord struggling with: {struggle}.
                    Give me a short, powerful reflection + a practical tip to help me lead better.
                    Keep it non-judgmental, honest, supportive, and focused on growth."""

        await interaction.response.defer(ephemeral=True)
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        await interaction.followup.send(response.choices[0].message.content, ephemeral=True)

class AskQuestionButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Ask your own question", style=discord.ButtonStyle.primary)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Please type your leadership question (any language is okay):", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", timeout=120.0, check=check)
            user_question = msg.content.strip()

            prompt = f"""A Discord community leader asked this question:\n\n{user_question}\n\n
                        Give a thoughtful, honest, practical response that shows empathy and clarity.
                        Keep it concise and supportive."""

            await interaction.followup.send("Processing your answer...", ephemeral=True)

            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8
            )

            await interaction.followup.send(response.choices[0].message.content, ephemeral=True)

        except Exception:
            await interaction.followup.send("❌ No question received in time. Try again later.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LeaderHelp(bot))
