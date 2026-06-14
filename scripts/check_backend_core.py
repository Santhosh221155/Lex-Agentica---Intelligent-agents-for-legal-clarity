import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
from app.main import app

client = TestClient(app)

for path in ['/', '/healthz', '/readyz']:
    response = client.get(path)
    print(path, response.status_code, response.json())
