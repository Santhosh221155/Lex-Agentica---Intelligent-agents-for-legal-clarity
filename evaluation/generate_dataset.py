import json

# Small synthetic dataset for Financial Intelligence Assistant
# Each item: {id, query, answer, relevant_docs}

SAMPLES = [
    {
        "id": f"q{i}",
        "query": q,
        "answer": a,
        "relevant_docs": docs,
    }
    for i, (q, a, docs) in enumerate([
        ("Why did Q3 cloud revenue drop after API pricing changes?",
         "Multiple causes: pricing changes, SMB churn, infra latency.",
         ["doc:pricing-memo", "doc:revenue-report-q3"]),
        ("Which customer segment saw the largest churn after pricing?",
         "SMB customers saw increased churn post pricing change.",
         ["doc:revenue-report-q3"]),
        ("What pricing changes were implemented in Q2?",
         "API tier price increases and new metering introduced.",
         ["doc:pricing-memo"]),
        ("Did infrastructure incidents coincide with revenue drops?",
         "Operational incidents were reported during the quarter.",
         ["doc:infra-incident-log"]),
        ("Show support complaint trends for Q3.",
         "Support tickets increased 20% in Q3, mainly about latency and billing.",
         ["doc:support-tickets-q3"]),
    ], start=1)
]

# Expand to ~50 by adding variations
base = SAMPLES.copy()
while len(SAMPLES) < 50:
    for s in base:
        if len(SAMPLES) >= 50:
            break
        new = s.copy()
        new_id = f"{s['id']}_v{len(SAMPLES)}"
        new['id'] = new_id
        # small paraphrase
        new['query'] = s['query'].replace('Q3', 'the third quarter') if 'Q3' in s['query'] else s['query']
        SAMPLES.append(new)

with open('evaluation/dataset.json', 'w', encoding='utf-8') as f:
    json.dump(SAMPLES, f, indent=2)

print('Wrote evaluation/dataset.json with', len(SAMPLES), 'samples')
