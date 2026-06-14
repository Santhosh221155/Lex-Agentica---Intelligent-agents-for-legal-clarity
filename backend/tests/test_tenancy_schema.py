import unittest

from app import models


class TenancySchemaTests(unittest.TestCase):
    def test_core_tables_have_tenant_workspace_columns(self):
        # Best-effort checks: ensure Table objects expose tenant/workspace columns
        table_names = [
            "documents",
            "chunks",
            "embeddings",
            "ingestion_jobs",
            "traces",
            "memories",
        ]
        for name in table_names:
            tbl = getattr(models, name, None)
            self.assertIsNotNone(tbl, f"Table {name} should exist in app.models")
            cols = {c.name for c in tbl.columns}
            self.assertIn("tenant_id", cols, f"{name} missing tenant_id")
            # workspace may be optional in some tables
            self.assertIn("workspace_id", cols, f"{name} missing workspace_id")


if __name__ == "__main__":
    unittest.main()
