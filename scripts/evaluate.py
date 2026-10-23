"""Count-based deterministic fixture benchmark; no model or infrastructure calls."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from app.rag import DATA, load_docs
from app.tools import query_batch_data, check_process_limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["all", "demo", "development", "holdout"], default="all")
    parser.add_argument("--output", default="runtime/evaluation/fixtures.json")
    args = parser.parse_args()
    manifest = json.loads((DATA / "dataset_manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((DATA / "batches.csv").read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        raise SystemExit("CSV SHA-256 differs from the manifest; regenerate deliberately and record the revision.")
    labels = json.loads((DATA / "batch_labels.json").read_text(encoding="utf-8"))
    docs = load_docs()
    rows = []
    for batch, expected in labels.items():
        if args.split != "all" and expected["split"] != args.split:
            continue
        started = time.perf_counter()
        result = check_process_limits(query_batch_data(batch), docs)
        findings, missing = len(result["findings"]), len(result["missing"])
        passed = not result["error"] and findings == expected["expected_findings"] and missing == expected["expected_missing"]
        rows.append({"batch_id": batch, "scenario": expected["scenario"], "split": expected["split"],
                     "expected_findings": expected["expected_findings"], "actual_findings": findings,
                     "expected_missing": expected["expected_missing"], "actual_missing": missing,
                     "passed": bool(passed), "elapsed_s": round(time.perf_counter() - started, 6)})
    if not rows:
        raise SystemExit("No fixture batches selected.")
    summary = {"benchmark": "deterministic_fixture_counts", "split": args.split,
               "dataset_sha256": digest, "total": len(rows), "passed": sum(r["passed"] for r in rows),
               "exact_count_agreement": sum(r["passed"] for r in rows) / len(rows), "model_calls": 0,
               "cases": rows, "limits": "Synthetic counts only; not end-to-end publication, model reasoning or external industrial accuracy."}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, ensure_ascii=False))
    if not all(r["passed"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
