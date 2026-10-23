"""Offline scenario evaluation; all generated files stay under --output."""
import argparse
import json
import time
from pathlib import Path
from app.config import Settings
from app.engine import TaskService
from app.reports import markdown_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runtime/evaluation")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=None, database_url="", redis_url="", milvus_uri="", use_llm=False)
    service = TaskService(output / "临时文件" / "evaluation-db", mode="langgraph", settings=settings)
    cases = [
        ("正常批次", "分析 B-101 参数", "B-101", "none", "completed"),
        ("超限批次", "分析 B-102 参数", "B-102", "none", "completed"),
        ("缺失参数", "分析 B-103 参数", "B-103", "none", "pending_review"),
        ("不存在批次", "分析 B-999 参数", "B-999", "none", "pending_review"),
        ("首次超时重试", "分析 B-102 参数", "B-102", "once", "completed"),
        ("持续超时", "分析 B-102 参数", "B-102", "always", "pending_review"),
        ("文档检索", "查询热压成型工艺规范", "", "none", "completed"),
        ("升温模型", "仿真升温并反算达到目标温度的时间", "", "none", "completed"),
    ]
    rows = []
    try:
        for name, q, batch, fault, expected in cases:
            start = time.perf_counter()
            result = service.create(q, batch, fault)
            passed = result["status"] == expected
            rows.append({"case": name, "expected": expected, "actual": result["status"],
                         "passed": passed, "elapsed_s": round(time.perf_counter() - start, 3),
                         "trace_events": len(result["trace"])})
            if name == "超限批次":
                (output / "示例-完整任务.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                (output / "示例-独立计算报告.md").write_text(markdown_report(result), encoding="utf-8")
        summary = {"engine": service.mode, "llm_used": False, "passed": sum(r["passed"] for r in rows), "total": len(rows),
                   "cases": rows, "scope": "固定模拟数据集的功能评测，不代表生产性能或工业精度"}
        (output / "场景评测.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
        if not all(r["passed"] for r in rows):
            raise SystemExit(1)
    finally:
        service.close()


if __name__ == "__main__":
    main()
