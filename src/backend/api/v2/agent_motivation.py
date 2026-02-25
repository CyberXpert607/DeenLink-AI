from groq import Groq
from config import MODEL

client = Groq()

MOTIVATION_PROMPT = """
You are an Islamic motivational assistant for DeenLink.

Rules:
- Use only provided sources.
- Be compassionate.
- Never fabricate.
"""


def stream_motivation_answer(messages: list):
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
