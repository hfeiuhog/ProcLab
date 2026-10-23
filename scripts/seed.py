"""Warm the actual embedding model and index all active knowledge."""
import json
from app.config import Settings
from app.rag import KnowledgeIndex


def main():
    index = KnowledgeIndex(Settings())
    try:
        print(json.dumps(index.reindex(), ensure_ascii=False))
        docs, info = index.search("热压成型温度压力黏度规范")
        if info["status"] != "ready":
            raise SystemExit("Knowledge retrieval is not ready")
        print(json.dumps({"retrieval": info, "documents": [d["doc_id"] for d in docs]}, ensure_ascii=False))
    finally:
        index.close()


if __name__ == "__main__":
    main()
