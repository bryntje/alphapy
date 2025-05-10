# quiz_tracker.py

import asyncpg
import config

class QuizTracker:
    def __init__(self):
        self.db_url = config.DATABASE_URL

    async def save_session(self, user_id: int, score: int, total_questions: int, answers: list):
        conn = await asyncpg.connect(self.db_url)

        # Insert de sessie
        session_id = await conn.fetchval("""
            INSERT INTO quiz_sessions (user_id, score, total_questions)
            VALUES ($1, $2, $3)
            RETURNING id;
        """, user_id, score, total_questions)

        # Insert alle antwoorden
        for a in answers:
            await conn.execute("""
                INSERT INTO quiz_answers (session_id, question, user_answer, correct_answer, is_correct, pip_type)
                VALUES ($1, $2, $3, $4, $5, $6);
            """, session_id, a["question"], a["user_answer"], a["correct_answer"], a["is_correct"], a["pip_type"])

        await conn.close()
