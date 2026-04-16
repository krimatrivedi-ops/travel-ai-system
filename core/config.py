from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "Travel AI System"
    environment: str = "development"
    debug: bool = True
    
    # Add this field so Pydantic recognizes the env variable
    groq_api_key: Optional[str] = None
    
    # Update the model to a Groq one since you are switching
    llm_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # llm_model: str = "llama-3.1-8b-instant"
    # llm_model: str = "llama-3.3-70b-versatile"
    
    # This configuration allows extra env vars without crashing, 
    # but it's better to explicitly define them as shown above.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra='ignore'  # This prevents the "Extra inputs" error in the future
    )

settings = Settings()