from groq import Groq
from config import GROQ_API_KEY, MODEL

client = Groq(api_key=GROQ_API_KEY)

def generate_answer(user_question: str, evidence: None, mode="knowledge") -> str:
    
    if mode == "chat":
        prompt = f"""
        You are Usman a friendly DeenLink Islamic APP assistant.
        You may engage in casual conversation.
        Do not issue religious rulings.
        Keep responses short and polite.

        User: {user_question}
        Assistant:
        """
    else:
        if not evidence:
            return "I cannot answer this based on the available sources"
        
        sources = "\n\n".join(
            f"Arabic:\n{e['arabic']}\n\nEnglish:\n{e['english']}\n(Source: {e['source']})"
            for e in evidence
        )


        prompt = f"""
        Answer ONLY using the provided sources.
        Do not add external information.

        Question:
        {user_question}

        Sources:
        {sources}

        Format:
        • Arabic
        • English
        • Explanation
        """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3 if mode == "knowledge" else 0.7,
    )
    return response.choices[0].message.content.strip()