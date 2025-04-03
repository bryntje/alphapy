class QuizState:
    def __init__(self):
        self.sessions = {}

    def start_session(self, user_id):
        self.sessions[user_id] = {
            "current_q": 0,
            "answers": [],
            "score": 0,
        }

    def record_answer(self, user_id, question, user_answer, correct_answer, is_correct, pip_type):
        state = self.sessions[user_id]
        state["answers"].append({
            "question": question,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "pip_type": pip_type
        })
        if is_correct:
            state["score"] += 1
        state["current_q"] += 1

    def end_session(self, user_id):
        return self.sessions.pop(user_id, None)
