# quiz_state.py

from typing import Dict, List, Optional

class QuizState:
    def __init__(self):
        self.sessions: Dict[int, Dict] = {}

    def start_session(self, user_id: int):
        self.sessions[user_id] = {
            "current_q": 0,
            "answers": [],
            "score": 0,
            "started_at": None  # optioneel tijd bijhouden
        }

    def record_answer(self, user_id: int, question: str, user_answer: str, correct_answer: str, is_correct: bool, pip_type: str):
        if user_id not in self.sessions:
            return

        self.sessions[user_id]["answers"].append({
            "question": question,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "pip_type": pip_type
        })

        if is_correct:
            self.sessions[user_id]["score"] += 1

        self.sessions[user_id]["current_q"] += 1

    def get_session(self, user_id: int) -> Optional[Dict]:
        return self.sessions.get(user_id)

    def end_session(self, user_id: int) -> Optional[Dict]:
        return self.sessions.pop(user_id, None)
