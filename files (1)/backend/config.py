"""Configuration — loads from environment / .env file."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Google / Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-live-001"  # Gemini 3.1 Flash Live
    gemini_ws_url: str = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""  # service_role key — bypasses RLS

    # App
    restaurant_name: str = "مطعم أبو خليل"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
