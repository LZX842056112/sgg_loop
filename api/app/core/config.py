import os
from functools import lru_cache
from dotenv import load_dotenv
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 使用当前路径的位置定位到项目的根目录位置
# print(Path(__file__).resolve().parents[4])
REPO_ROOT = Path(__file__).resolve().parents[4]

# 加载.env中的内容
load_dotenv(REPO_ROOT / ".env")


# 打印读取到的LLM_TIMEOUT_SECONDS
# print(os.getenv("LLM_TIMEOUT_SECONDS"))

# 设置配置对象
class Settings(BaseSettings):
    """应用配置固定从仓库根目录获取,避免不同启动目录导致配置漂移  添加所有项目中需要使用到的常量配置"""
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8-sig", extra="ignore")
    # 应用名称 自定义变量
    app_name: str = "Loop Engineering API"

    # 环境env变量  使用pydantic-setting可以自动读取环境变量的值 不需要显示调用 os.getenv 最好是有一个初始化的赋值
    database_url: str = ""
    workspace_root: Path = ""
    next_public_api_base_url: str = ""
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_api_key: str | None = None
    llm_model: str = ""
    llm_api_key_required: bool = False
    llm_timeout_seconds: int = 0

    # 常量值
    source_max_file_bytes: int = 1_000_000
    source_excerpt_chars: int = 4_000
    web_fetch_timeout_seconds: float = 20.0
    git_clone_timeout_seconds: float = 120.0

    @model_validator(mode="after")
    def normalize_paths(self) -> "Settings":
        """相对运行目录会漂移 路径配置统一改为绝对路径  使用仓库根目录解析"""
        if not self.workspace_root.is_absolute():
            self.workspace_root = (REPO_ROOT / self.workspace_root).resolve()

        if self.llm_timeout_seconds < 5:
            self.llm_timeout_seconds = 5

        return self


# 注解lru_cache表示返回的对象是一个单例对象  => 如果不是第一次调用 就直接返回之前的对象
@lru_cache
def get_settings() -> Settings:
    print("hello")
    return Settings()

# settings = get_settings()
# settings1 = get_settings()
# settings2 = get_settings()
# print(settings.LLM_base_url)
# print(settings.workspace_root)
