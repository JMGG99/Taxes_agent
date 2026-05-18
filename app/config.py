from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_url_readonly: str
    azure_ai_endpoint: str
    azure_model_deployment: str
    azure_ai_api_key: str

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_file_override": False,  # system env vars take priority over .env
    }


settings = Settings()
