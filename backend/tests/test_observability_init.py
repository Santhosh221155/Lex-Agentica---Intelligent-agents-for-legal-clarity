import unittest


class ObservabilityInitTests(unittest.TestCase):
    def test_init_opentelemetry_no_throw_when_missing_packages(self):
        try:
            # Import locally to avoid side-effects at module import time
            from app.observability import init_opentelemetry

            ok = init_opentelemetry(service_name="test_service")
            # If packages missing, function returns False; if present, True
            self.assertIn(ok, (True, False))
        except Exception as e:
            self.fail(f"init_opentelemetry raised unexpectedly: {e}")


if __name__ == "__main__":
    unittest.main()
