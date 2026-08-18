from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stackforge_admin_email: str
    stackforge_admin_password: str
    database_url: str
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = ""
    default_model: str = "gpt-4o"
    projects_root: str = "/data/projects"
    preview_base_domain: str = "localhost"
    max_concurrent_previews: int = 3
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    cookie_secure: bool = False
    max_context_size: int = 120000
    stackforge_runner_url: str = "http://stackforge-runner:9000"
    stackforge_templates_root: str = "/templates"
    stackforge_runner_token: str


settings = Settings()
