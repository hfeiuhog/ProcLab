"""Check tracked public files for private-state paths and common credential formats."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "api_token": re.compile(rb"\bsk-[A-Za-z0-9_-]{28,}\b"),
}
PRIVATE_DIRS = {".venv", "runtime", "backups", "tls", "tls-logs", "artifacts", ".cache", "__pycache__"}


def main():
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    if tracked.returncode == 0:
        paths = [ROOT / p.decode("utf-8") for p in tracked.stdout.split(b"\0") if p]
    else:
        paths = [p for p in ROOT.rglob("*") if p.is_file() and not any(x in {".git", *PRIVATE_DIRS} for x in p.relative_to(ROOT).parts)]
    findings = []
    for path in paths:
        rel = path.relative_to(ROOT)
        if any(p in PRIVATE_DIRS for p in rel.parts) or (path.name.startswith(".env") and path.name != ".env.example"):
            findings.append({"file": rel.as_posix(), "rule": "private_state_path"})
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}:
            findings.append({"file": rel.as_posix(), "rule": "private_state_type"})
        content = path.read_bytes()
        for name, pattern in RULES.items():
            if pattern.search(content):
                findings.append({"file": rel.as_posix(), "rule": name})
    print(json.dumps({"checked_files": len(paths), "findings": findings, "scope": "Heuristic tracked-file check; not a guarantee against all secrets."}))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
