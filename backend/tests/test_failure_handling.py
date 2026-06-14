import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.main import app
from app.agents import planner, retrieval


class FailureHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_falls_back_on_invalid_json(self):
        with patch('app.agents.planner.call_planning_model', new=AsyncMock(return_value='not-json')):
            plan = await planner.plan('Why did revenue drop?', 'user:local')

        self.assertEqual(plan['query'], 'Why did revenue drop?')
        self.assertEqual(plan['user_id'], 'user:local')
        self.assertEqual(plan['retrieval_strategy'], 'hybrid')
        self.assertIn({'id': 'retrieve', 'agent': 'retrieval'}, plan['steps'])
        self.assertIn('requires_validation', plan)

    async def test_retrieval_returns_warning_when_empty(self):
        result = await retrieval.retrieve('pricing change memo', {'retrieval_strategy': 'hybrid', 'max_docs': 8})

        self.assertEqual(result['source'], 'hybrid')
        self.assertEqual(result.get('chunks'), [])
        self.assertIn('warning', result)

    async def test_query_endpoint_returns_503_when_orchestrate_fails(self):
        with patch('app.main.orchestrate', new=AsyncMock(side_effect=RuntimeError('boom'))):
            client = TestClient(app)
            response = client.post('/api/query', json={'query': 'hello'})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'orchestration_failed')

    async def test_stream_endpoint_returns_error_event_on_orchestrate_failure(self):
        with patch('app.main.orchestrate', new=AsyncMock(side_effect=RuntimeError('boom'))):
            client = TestClient(app)
            response = client.get('/api/stream-query?q=hello')

        self.assertEqual(response.status_code, 503)
        self.assertIn('orchestration_failed', response.text)


if __name__ == '__main__':
    unittest.main()
