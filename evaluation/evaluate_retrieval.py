import asyncio
import json
import time
from typing import List

from app.agents import retrieval


def precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    topk = retrieved_ids[:k]
    if not topk:
        return 0.0
    return sum(1 for x in topk if x in relevant_ids) / len(topk)


def recall_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    topk = retrieved_ids[:k]
    if not relevant_ids:
        return 0.0
    return sum(1 for x in topk if x in relevant_ids) / len(relevant_ids)


async def evaluate(dataset_path: str = 'evaluation/dataset.json', k: int = 5):
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    precisions = []
    recalls = []
    latencies = []

    plan = {"retrieval_strategy": "hybrid", "max_docs": k}

    for item in dataset:
        q = item['query']
        relevant = item.get('relevant_docs', [])
        t0 = time.time()
        res = await retrieval.retrieve(q, plan)
        latency = time.time() - t0
        latencies.append(latency)

        retrieved = [d.get('chunk_id') for d in (res.get('chunks') or []) if d.get('chunk_id')]
        precisions.append(precision_at_k(retrieved, relevant, k))
        recalls.append(recall_at_k(retrieved, relevant, k))

    return {
        'precision_at_5': sum(precisions)/len(precisions) if precisions else 0.0,
        'recall_at_5': sum(recalls)/len(recalls) if recalls else 0.0,
        'avg_latency_sec': sum(latencies)/len(latencies) if latencies else 0.0,
        'num_queries': len(dataset),
    }


if __name__ == '__main__':
    print('Run via run_evaluation.py')
