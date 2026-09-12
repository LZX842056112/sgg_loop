"""验证配置能否正确读取 .env —— 运行后删除即可。"""
from app.core.config import get_settings

s = get_settings()

print("app_name:           ", s.app_name)
print("database_url:       ", s.database_url)
print("workspace_root:     ", s.workspace_root)
print("llm_provider:       ", s.llm_provider)
print("llm_model:          ", s.llm_model or "(未配置)")
print("llm_timeout_seconds:", s.llm_timeout_seconds)
print("source_max_file_bytes:", s.source_max_file_bytes)
