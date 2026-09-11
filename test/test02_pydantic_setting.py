from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    project_root_path: Path = Path(__file__).parent.parent
    # 调用时候的路径拼接代码的路径= 文件所处的路径
    model_config = SettingsConfigDict(env_file=project_root_path / ".env", env_file_encoding="utf-8")

    database_url: str = ''
    llm_provider: str = ''


settings = Settings()
print(settings.database_url)
print(settings.llm_provider)
print(settings.project_root_path)
