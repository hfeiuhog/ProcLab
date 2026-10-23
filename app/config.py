from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    runtime_dir: str = "runtime"
    database_url: str = Field(default="", repr=False)
    redis_url: str = Field(default="", repr=False)
    milvus_uri: str = ""
    milvus_token: str = Field(default="", repr=False)
    milvus_collection: str = "process_knowledge_v2"
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = Field(default=512, ge=64, le=4096)
    embedding_api_key: str = Field(default="", repr=False)
    embedding_base_url: str = ""
    embedding_batch_size: int = Field(default=8, ge=1, le=32)
    retrieval_candidates: int = Field(default=12, ge=3, le=32)
    retrieval_limit: int = Field(default=4, ge=2, le=8)
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    use_llm: bool = False
    model_provider: str = "openai"
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_api_key: str = Field(default="", repr=False)
    agent_model: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    high_risk_extract_model: str = "Qwen/Qwen3.5-35B-A3B"
    rule_reasoning_model: str = "deepseek-ai/DeepSeek-V4-Pro"
    vision_fallback_model: str = "PaddlePaddle/PaddleOCR-VL-1.5"
    vision_precision_model: str = "PaddlePaddle/PaddleOCR-VL-1.6"
    complex_vision_model: str = "Qwen/Qwen3-VL-8B-Instruct"
    paddle_official_api_key: str = Field(default="", repr=False)
    paddle_official_base_url: str = "https://paddleocr.aistudio-app.com"
    document_max_bytes: int = Field(default=4_000_000, ge=1024, le=8_000_000)
    document_daily_limit: int = Field(default=10, ge=0, le=100)
    document_poll_timeout: int = Field(default=90, ge=10, le=180)
    document_enabled: bool = True
    speech_enabled: bool = True
    speech_model: str = "FunAudioLLM/SenseVoiceSmall"
    model_timeout: int = Field(default=40, ge=5, le=120)
    model_max_tokens: int = Field(default=1200, ge=128, le=4096)
    openai_api_key: str = Field(default="", repr=False)
    openai_base_url: str = ""
    openai_model: str = ""
    superagent_enabled: bool = True
    graph_mode: str = "langgraph"
    api_token: str = Field(default="", repr=False)
    app_env: str = "development"
    auth_enabled: bool = False
    registration_enabled: bool = True
    admin_username: str = 'admin'
    admin_password_hash: str = Field(default='', repr=False)
    hr_username: str = 'hr'
    hr_password_hash: str = Field(default='', repr=False)
    session_ttl_seconds: int = Field(default=43200, ge=300, le=604800)
    demo_daily_tasks: int = Field(default=30, ge=1, le=1000)
    demo_global_daily_tasks: int = Field(default=100, ge=1, le=10000)
    harness_max_tool_calls: int = Field(default=12, ge=3, le=20)
    harness_timeout_seconds: int = Field(default=180, ge=20, le=600)
    harness_max_repairs: int = Field(default=2, ge=1, le=5)
    max_workers: int = Field(default=2, ge=1, le=8)
    short_memory_ttl: int = Field(default=86400, ge=60)
    allow_fault_injection: bool = True
    local_temp_dir: str = ""
    uv_cache_dir: str = "runtime/cache/uv"
    uv_python_install_dir: str = "runtime/tools/python"
    uv_tool_dir: str = "runtime/tools/uv"

    @model_validator(mode="after")
    def provider_aliases(self):
        # Preserve the former OpenAI-compatible configuration for existing deployments/tests.
        if self.model_provider == "siliconflow" and self.siliconflow_api_key:
            self.openai_api_key = self.siliconflow_api_key
            self.openai_base_url = self.siliconflow_base_url
            self.openai_model = self.agent_model
        if self.embedding_provider == 'siliconflow' and self.siliconflow_api_key:
            self.embedding_api_key = self.siliconflow_api_key
            self.embedding_base_url = self.siliconflow_base_url
        return self

    def check(self):
        if self.auth_enabled and (not self.admin_password_hash or self.admin_username == self.hr_username):
            raise ValueError('AUTH_ENABLED requires administrator password hash and distinct account names')
        if self.embedding_provider not in ("hash", "openai", "fastembed", "siliconflow"):
            raise ValueError("EMBEDDING_PROVIDER must be fastembed/hash/openai/siliconflow")
        if self.app_env == "production" and (len(self.api_token) < 24 or not self.database_url or not self.redis_url or not self.milvus_uri):
            raise ValueError("Production needs API_TOKEN (24+ chars), DATABASE_URL, REDIS_URL and MILVUS_URI")
        return self
