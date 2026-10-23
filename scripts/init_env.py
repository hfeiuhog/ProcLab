"""Idempotent setup; preserves model credentials and never prints secrets."""
import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values, set_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "docker-dev", "production"], default="local")
    args = parser.parse_args()
    path = Path(".env")
    if not path.exists():
        path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    config = dotenv_values(path)
    def put(k, v):
        set_key(path, k, v)
        config[k] = v
    for name in ["MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD"]:
        if not config.get(name):
            put(name, secrets.token_urlsafe(32))
    if args.mode == "production" and not config.get("API_TOKEN"):
        put("API_TOKEN", secrets.token_urlsafe(32))
    put("APP_ENV", "production" if args.mode == "production" else "development")
    put("ALLOW_FAULT_INJECTION", "false" if args.mode == "production" else "true")
    if args.mode != "local":
        dbhost, redishost, vectorhost = ("mysql:3306", "redis:6379", "milvus:19530") if args.mode == "production" else ("127.0.0.1:13306", "127.0.0.1:16379", "127.0.0.1:19530")
        put("DATABASE_URL", f"mysql+pymysql://industrial:{config['MYSQL_PASSWORD']}@{dbhost}/industrial?charset=utf8mb4")
        put("REDIS_URL", f"redis://:{config['REDIS_PASSWORD']}@{redishost}/0")
        put("MILVUS_URI", f"http://{vectorhost}")
    else:
        for name in ["DATABASE_URL", "REDIS_URL", "MILVUS_URI"]:
            put(name, "")
    if not config.get('ADMIN_PASSWORD_HASH') or not config.get('HR_PASSWORD_HASH'):
        subprocess.run([sys.executable,'-m','scripts.setup_access']+(['--server'] if args.mode=='production' else []),check=True)
    if os.name != "nt":
        path.chmod(0o600)
    print(f"Initialized {args.mode} configuration. Credentials are in .env (not printed).")


if __name__ == "__main__":
    main()
