import unittest
import sys
import os

# Ensure repo root is on path for imports
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import models


class MultiTenancySchemaTest(unittest.TestCase):
    def test_tenant_and_workspace_tables_exist(self):
        meta = models.metadata
        self.assertIn('tenants', meta.tables)
        self.assertIn('workspaces', meta.tables)

    def test_core_tables_have_tenant_workspace_columns(self):
        meta = models.metadata
        # documents should have both tenant_id and workspace_id
        self.assertIn('documents', meta.tables)
        docs_cols = meta.tables['documents'].c
        self.assertIn('tenant_id', docs_cols)
        self.assertIn('workspace_id', docs_cols)

        # chunks
        self.assertIn('chunks', meta.tables)
        chunks_cols = meta.tables['chunks'].c
        self.assertIn('tenant_id', chunks_cols)
        self.assertIn('workspace_id', chunks_cols)

        # embeddings
        self.assertIn('embeddings', meta.tables)
        emb_cols = meta.tables['embeddings'].c
        self.assertIn('tenant_id', emb_cols)
        self.assertIn('workspace_id', emb_cols)


if __name__ == '__main__':
    unittest.main()
