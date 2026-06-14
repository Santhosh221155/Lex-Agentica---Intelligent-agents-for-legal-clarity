from __future__ import annotations

from typing import Any, Dict, Iterable, List


try:
    from ragas import evaluate as ragas_evaluate  # type: ignore
except Exception:
    ragas_evaluate = None

try:
    from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric  # type: ignore
except Exception:
    HallucinationMetric = None
    AnswerRelevancyMetric = None


def _tokenize(text: str) -> List[str]:
    import re

    return [token for token in re.split(r"\W+", (text or "").lower()) if len(token) >= 2]


def _support_terms(question: str, contexts: Iterable[Dict[str, Any]]) -> List[str]:
    question_terms = set(_tokenize(question))
    context_terms = set()
    for context in contexts:
        context_terms.update(_tokenize(context.get("content", "")))
    return sorted(question_terms.intersection(context_terms))


def compute_context_precision(question: str, contexts: List[Dict[str, Any]]) -> float:
    if not contexts:
        return 0.0
    support_counts = []
    question_terms = set(_tokenize(question))
    for context in contexts:
        context_terms = set(_tokenize(context.get("content", "")))
        support_counts.append(len(question_terms.intersection(context_terms)) / max(1, len(context_terms)))
    return round(sum(support_counts) / len(support_counts), 4)


def compute_context_recall(question: str, contexts: List[Dict[str, Any]]) -> float:
    question_terms = set(_tokenize(question))
    if not question_terms:
        return 0.0
    supported = _support_terms(question, contexts)
    return round(len(supported) / len(question_terms), 4)


def compute_answer_relevancy(question: str, answer: str) -> float:
    question_terms = set(_tokenize(question))
    answer_terms = set(_tokenize(answer))
    if not question_terms:
        return 0.0
    return round(len(question_terms.intersection(answer_terms)) / len(question_terms), 4)


def compute_faithfulness(answer: str, contexts: List[Dict[str, Any]]) -> float:
    if not answer.strip():
        return 0.0
    context_text = " ".join(context.get("content", "") for context in contexts).lower()
    answer_terms = _tokenize(answer)
    if not answer_terms:
        return 0.0
    grounded = sum(1 for term in answer_terms if term in context_text)
    return round(grounded / len(answer_terms), 4)


def compute_hallucination_score(answer: str, contexts: List[Dict[str, Any]]) -> float:
    return round(1.0 - compute_faithfulness(answer, contexts), 4)


def compute_answer_quality_score(question: str, answer: str, contexts: List[Dict[str, Any]]) -> float:
    relevancy = compute_answer_relevancy(question, answer)
    faithfulness = compute_faithfulness(answer, contexts)
    precision = compute_context_precision(question, contexts)
    return round((relevancy * 0.4) + (faithfulness * 0.4) + (precision * 0.2), 4)


def compute_metric_bundle(question: str, contexts: List[Dict[str, Any]], answer: str) -> Dict[str, float]:
    return {
        "faithfulness": compute_faithfulness(answer, contexts),
        "context_precision": compute_context_precision(question, contexts),
        "context_recall": compute_context_recall(question, contexts),
        "answer_relevancy": compute_answer_relevancy(question, answer),
        "hallucination_score": compute_hallucination_score(answer, contexts),
        "answer_quality_score": compute_answer_quality_score(question, answer, contexts),
    }
