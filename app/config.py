from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str = ""
    groq_api_key: str = ""
    database_url: str = "sqlite:///local.db"
    dashboard_token: str = "dev-token"
    base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env"}

settings = Settings()
