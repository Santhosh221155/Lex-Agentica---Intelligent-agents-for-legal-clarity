from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
from app.main import app

client = TestClient(app)

print('requesting POST /api/query {query: hello}')
resp = client.post('/api/query', json={'query': 'hello'})
print('status_code=', resp.status_code)
try:
	j = resp.json()
	print('json keys:', list(j.keys()))
	print('plan snippet:', str(j.get('plan'))[:1000])
	print('first_chunk:', j.get('first_chunk'))
except Exception:
	print('response text:', resp.text[:1000])
