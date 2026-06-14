Evaluation pipeline

This folder contains tools to generate a benchmark dataset of QA pairs and run retrieval + faithfulness evaluation for the Financial Intelligence Assistant.

Scripts:
- `generate_dataset.py` — create a 50-sample benchmark `dataset.json` (domain-specific QA with relevance labels).
- `evaluate_retrieval.py` — compute retrieval metrics (Precision@k, Recall@k, avg latency).
- `run_evaluation.py` — runs the full evaluation pipeline and prints a summary.

Run:
```powershell
python evaluation/generate_dataset.py
python evaluation/run_evaluation.py
```
