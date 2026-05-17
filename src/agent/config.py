from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal


class ShortTermConfig(BaseModel):
    """短期上下文配置"""
    max_tokens: int = 128000
    trigger_threshold: float = 0.7
    keep_recent: int = 5
    preserve_system: bool = True
    max_steps: int = 50
    max_iterations: int = 50
    model_config = ConfigDict(extra="ignore")


class LongTermConfig(BaseModel):
    """长期上下文配置"""
    memory_dir: Path = Path("./memory")
    session_ttl_days: int = 7
    vector_enabled: bool = True
    vector_dimension: int = 1536
    chroma_persist_dir: str = "./memory/chroma"
    model_config = ConfigDict(extra="ignore")


class InitializationConfig(BaseModel):
    """初始化配置"""
    resume_on_startup: bool = True
    load_recent_sessions: int = 5
    load_memory: bool = True
    search_similar: bool = True
    model_config = ConfigDict(extra="ignore")


class AgentConfig(BaseSettings):
    """Agent 完整配置"""
    model: str = "openai:gpt-4"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"

    short_term: ShortTermConfig = ShortTermConfig()
    long_term: LongTermConfig = LongTermConfig()
    initialization: InitializationConfig = InitializationConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        extra="ignore",
    )


DEFAULT_CONFIG = AgentConfig()