from google.genai import types


SYSTEM_INSTRUCTION = "You are an e-commerce customer support agent."


def user_prompt(text: str) -> types.Content:
    return types.Content(
        role="user",
        parts=[types.Part.from_text(text=text)],
    )