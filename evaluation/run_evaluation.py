import asyncio
import json
from evaluation.evaluate_retrieval import evaluate
from app.agents import validator


async def run_all():
    retrieval_stats = await evaluate('evaluation/dataset.json', k=5)

    # Basic faithfulness check: for each query, ask validator whether retrieval has evidence
    # This uses the validator.validate stub to detect missing evidence
    with open('evaluation/dataset.json','r',encoding='utf-8') as f:
        dataset = json.load(f)

    issues = 0
    for item in dataset:
        q = item['query']
        plan = {"retrieval_strategy": "hybrid", "max_docs": 5}
        res = await validator.validate(q, plan, retrieval_res=None, tools_res=None, memory_res=None)
        if res and res.get('issues'):
            issues += 1

    faithfulness = 1.0 - (issues / len(dataset)) if dataset else 0.0

    results = {
        'retrieval': retrieval_stats,
        'faithfulness_estimate': faithfulness,
    }
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(run_all())
