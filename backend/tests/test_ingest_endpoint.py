import asyncio
import unittest
import tempfile
import os
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.api import ingest as ingest_api


class IngestEndpointTests(unittest.TestCase):
    def test_ingest_file_endpoint_enqueues_job(self):
        client = TestClient(app)

        # Mock document_store.create_ingestion_job to avoid DB calls
        with patch("app.services.document_store.create_ingestion_job", new=AsyncMock(return_value=123)):
            # Mock background task scheduling by posting a small file
            files = {"file": ("test.pdf", b"%PDF-1.4\nhello world")}
            resp = client.post("/api/ingest/file?user_id=user:local", files=files)
            # We accept 200 or 202 depending on implementation
            self.assertIn(resp.status_code, (200, 202))

    def test_process_file_job_advances_statuses(self):
        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            ingest_api.JOBS["job-1"] = {"status": "queued"}
            try:
                with patch("app.api.ingest.update_ingestion_job", new=AsyncMock()) as mock_update:
                    with patch(
                        "app.api.ingest.dispatch_ingest_file",
                        new=AsyncMock(return_value={"status": "success", "chunks_stored": 1}),
                    ):
                        await ingest_api._process_file_job(
                            job_id="job-1",
                            db_job_id=7,
                            path=path,
                            user_id=1,
                            document_id=2,
                        )

                    self.assertEqual(ingest_api.JOBS["job-1"]["status"], "completed")
                    self.assertEqual(ingest_api.JOBS["job-1"]["result"]["status"], "success")
                    self.assertEqual(mock_update.await_args_list[0].args, (7, "processing"))
                    self.assertEqual(mock_update.await_args_list[-1].args, (7, "completed", None))
            finally:
                ingest_api.JOBS.pop("job-1", None)
                if os.path.exists(path):
                    os.remove(path)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
