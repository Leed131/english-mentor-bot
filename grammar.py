import os
import json

USER_DATA_DIR = "user_data"

def log_interaction(user_id, interaction_type, content):
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    file_path = os.path.join(USER_DATA_DIR, f"{user_id}.json")

    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append({"type": interaction_type, "content": content})

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
def correct_grammar(text):
    # Пока возвращает тот же текст. Позже добавим проверку и исправления.
    return text
