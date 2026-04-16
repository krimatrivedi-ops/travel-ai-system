import os
from groq import Groq  # Switched from openai
from typing import Optional
from dotenv import load_dotenv
from core.config import settings

load_dotenv()
# Initialize Groq client using the GROQ_API_KEY environment variable
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Calls the Groq API with the provided system and user prompts.
    Returns the LLM response as a JSON string.
    """
    try:
        response = client.chat.completions.create(
            # Using the Groq-specific model ID
            model=settings.llm_model, 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            # Ensure the system prompt instructs the model to return JSON
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        # Better logging for debugging API issues
        print(f"Groq API Error: {e}")
        return '{"error": "LLM call failed"}'