"""Isolated loopback demo for documentation: synthetic inputs, no model credentials."""
import argparse
from pathlib import Path
import uvicorn
from app.api import create_app
from app.config import Settings
from app.engine import TaskService


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--runtime", default="runtime/documentation-demo")
    args = p.parse_args()
    runtime = Path(args.runtime).resolve()
    settings = Settings(_env_file=None, runtime_dir=str(runtime), local_temp_dir=str(runtime / "tmp"),
                        database_url="", redis_url="", milvus_uri="", use_llm=False,
                        auth_enabled=False, registration_enabled=False, api_token="",
                        openai_api_key="", siliconflow_api_key="", embedding_api_key="",
                        paddle_official_api_key="", document_enabled=False, speech_enabled=False,
                        embedding_provider="hash", allow_fault_injection=True)
    service = TaskService(runtime, "fallback", llm_enabled=False, settings=settings)
    try:
        if not service.store.list_conversations():
            service.create("分析 B-102 批次的温度、压力和黏度，列出超限证据。", "B-102", intent="batch")
            service.create("按设备统计全部模拟批次的超限批次比例", intent="analytics")
    finally:
        service.close()
    uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
