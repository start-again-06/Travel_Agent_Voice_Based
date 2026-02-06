"""Configuration management for Voice Travel Agent."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    elevenlabs_api_key: str
    groq_api_key: str
    resend_api_key: str = ""
    pinecone_api_key: str = ""
    foursquare_service_api_key: str = ""
    foursquare_client_id: str = ""
    foursquare_client_secret: str = ""

    # ElevenLabs Settings
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # Bella voice (warm, friendly)
    elevenlabs_model_id: str = "eleven_turbo_v2_5"  # Fastest model

    # Email Settings
    email_sender: str = "onboarding@resend.dev"  # Default sender for Resend
    email_sender_name: str = "Voice Travel Agent"

    # Model Cache Settings
    sentence_transformers_home: str = "./models"  # Path to cache sentence transformer models

    # Server Settings
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Voice Settings
    max_recording_duration: int = 60  # seconds
    websocket_timeout: int = 600  # seconds

    # Logging
    log_level: str = "INFO"

    # LangSmith Settings
    langsmith_tracing: str = "true"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "voice_agent"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


# Global settings instance
settings = Settings()
