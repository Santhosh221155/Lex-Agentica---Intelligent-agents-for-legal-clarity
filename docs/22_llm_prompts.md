# LLM Prompts

This document lists all prompts used by the RAG system for different LLM interactions.

## 1. Planner Prompt

**File**: `backend/app/agents/planner.py`

**Purpose**: Decomposes user queries into a structured plan for agent execution.

```
Given the user query, decompose the task into agents (retrieval, tools, memory, validator, synthesizer), decide if validation is required, choose a retrieval strategy, infer metadata filters when relevant, and return a JSON object with keys: query, user_id, steps (array of {id,agent}), requires_validation (bool), retrieval_strategy, max_docs, retrieval_filters.
User query: {query}
```

## 2. Synthesizer Prompt

**File**: `backend/app/agents/synthesizer.py`

**Purpose**: Generates user-facing answers based on retrieved document chunks.

```
Answer ONLY based on the provided document excerpts. If the answer is not in the excerpts, say so explicitly. Never use outside knowledge.
User query: {query}
Document excerpts:
- Source: {source}, Page: {page}, Score: {score}: {content[:500]}
```

## 3. Reflection Prompt

**File**: `backend/app/services/reflection.py`

**Purpose**: Reviews generated answers for quality, evidence, and potential hallucinations.

```
You are a reflection agent. Review the answer for missing evidence, weak citations, or hallucinations. Return a short JSON object with keys: critique, missing_evidence, weak_citations, hallucination_flags, revised_answer, confidence.
```

## Notes

- All prompts are designed to work with the agent architecture
- The synthesizer prompt includes source metadata for internal use only
- Output sanitization ensures citations and source information are not included in final user responses
- The planner uses Redis caching for repeated queries to reduce latency
