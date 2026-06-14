
import sys
from pathlib import Path
backend_root = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_root))
from app.services.security import clean_llm_response

test = "According to the document, the CGPA is 7.60 up to the 5th semester."
print(f"Original: {test}")
print(f"Cleaned: {clean_llm_response(test)}")
