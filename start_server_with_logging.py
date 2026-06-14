import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath("backend"))

# Configure logging to write to a file
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="server_debug.log",
    filemode="w"
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

logger = logging.getLogger(__name__)

logger.info("Starting server...")

try:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )
except Exception as e:
    logger.exception("Server failed to start")
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
