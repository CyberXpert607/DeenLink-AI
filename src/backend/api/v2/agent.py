from groq import Groq
from config import MODEL, GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY, timeout=120.0)


def stream_chat_response(messages: list):
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta