import discord
from discord.ext import commands
from discord import app_commands

from utils.quiz_state import QuizState
from utils.quiz_tracker import QuizTracker

quiz_state = QuizState()
tracker = QuizTracker()

class AILotQuiz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lotquiz", description="Test your risk management across 3 forex scenarios.")
    async def lotquiz(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        # Start new session
        quiz_state.start_session(user_id)

        questions = [
            {
                "question": "**Q1:** EUR/USD\nAccount: $10,000\nRisk: 2%\nStop loss: 50 pips",
                "correct": 0.4,
                "pip_type": "major",
                "tolerance": 0.02
            },
            {
                "question": "**Q2:** USD/JPY @ 145.00\nAccount: $5,000\nRisk: 1.5%\nStop loss: 60 pips",
                "correct": 0.55,  # Afgerond op basis van $0.91 per micro lot (0.0091 per pip per lot)
                "pip_type": "jpy",
                "tolerance": 0.03
            },
            {
                "question": "**Q3:** XAU/USD\nAccount: $7,500\nRisk: 1%\nStop loss: 2.5",
                "correct": 0.3,  # Pip value for gold ≈ $10 per lot per 1.0 move
                "pip_type": "xau",
                "tolerance": 0.03
            }
        ]

        await interaction.response.send_message("🎯 Starting your lot size challenge...\nYou'll get 3 questions.", ephemeral=True)

        for q in questions:
            await interaction.followup.send(q["question"], ephemeral=True)

            def check(m):
                return m.author.id == user_id and m.channel == interaction.channel

            try:
                msg = await self.bot.wait_for("message", timeout=60.0, check=check)
                try:
                    user_answer = float(msg.content)
                except ValueError:
                    await interaction.followup.send("⚠️ That's not a number. Skipping...", ephemeral=True)
                    user_answer = None

                if user_answer is not None:
                    diff = abs(user_answer - q["correct"])
                    is_correct = diff <= q["tolerance"]
                    if is_correct:
                        await interaction.followup.send("✅ Correct! You're on fire 🔥", ephemeral=True)
                    else:
                        await interaction.followup.send(f"❌ Not quite. Correct: **{q['correct']} lots**", ephemeral=True)

                    quiz_state.record_answer(
                        user_id=user_id,
                        question=q["question"],
                        user_answer=str(user_answer),
                        correct_answer=str(q["correct"]),
                        is_correct=is_correct,
                        pip_type=q["pip_type"]
                    )
            except Exception:
                await interaction.followup.send("⌛ Time’s up for this question!", ephemeral=True)

        # Final result
        session = quiz_state.end_session(user_id)
        if session:
            score = session["score"]
            total = len(session["answers"])
            await tracker.save_session(user_id, score, total, session["answers"])
            await interaction.followup.send(f"🏁 Quiz complete! Your score: **{score}/{total}**", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Session tracking failed.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AILotQuiz(bot))
