import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings

@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, use_llm=False, database_url='', redis_url='', milvus_uri='')
    with TestClient(create_app(tmp_path,graph_mode='fallback',settings=settings)) as c:
        yield c


@pytest.fixture(autouse=True)
def isolate_settings_environment():
    # Some database SDK imports load .env into os.environ. Unit settings that opt
    # out of .env must not inherit real integration credentials from an earlier test.
    import os
    names={name.upper() for name in Settings.model_fields}
    original={name:os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name,None)
    try:
        yield
    finally:
        for name,value in original.items():
            if value is None:
                os.environ.pop(name,None)
            else:
                os.environ[name]=value
