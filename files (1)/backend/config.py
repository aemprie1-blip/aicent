from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-realtime"
    openai_ws_url: str = "wss://api.openai.com/v1/realtime"
    openai_voice: str = "ash"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # App
    restaurant_name: str = "\u0645\u0637\u0639\u0645 \u0623\u0628\u0648 \u062e\u0644\u064a\u0644"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
