import os

BASE_PATH = "data/prompts"

async def load_topic_context(topic: str) -> str:
    """
    Laadt contextuele uitleg op basis van een topic keyword (zoals 'rsi')
    uit een .md of .txt bestand in /data/prompts/.
    """
    filename = topic.lower().replace(" ", "_") + ".md"
    file_path = os.path.join(BASE_PATH, filename)

    if not os.path.exists(file_path):
        return ""

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()
