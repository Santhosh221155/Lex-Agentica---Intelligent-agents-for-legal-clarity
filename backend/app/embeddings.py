import os
import logging
from typing import List
import numpy as _np

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# Lazy loading - load only when first needed
_model = None


def get_model():
    global _model
    if _model is None:
        logger.info("Loading SentenceTransformer model: %s", MODEL_NAME)
        from sentence_transformers import SentenceTransformer  # type: ignore
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("✓ SentenceTransformer model loaded: %s", MODEL_NAME)
    return _model


def warm_embedding_model():
    return get_model()


def embed_texts(texts: List[str]):
    if _model is None:
        get_model()
    return _model.encode(texts, show_progress_bar=False, convert_to_numpy=True).tolist()


def embed_text(text: str):
    return embed_texts([text])[0]
