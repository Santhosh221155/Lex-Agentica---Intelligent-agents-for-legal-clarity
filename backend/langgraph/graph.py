"""Build a LangGraph orchestration describing the Agentic RAG workflow.

This module attempts to build a graph if `langgraph` is installed. The graph contains:
- planner -> parallel (retrieval, tools, memory) -> optional validator -> synthesizer

The implementation is defensive so the codebase remains runnable even when `langgraph` is not available.
"""
try:
    from langgraph import Graph
except Exception:
    Graph = None

from app.agents import planner as planner_agent
from app.agents import retrieval as retrieval_agent
from app.agents import tool_agent as tool_agent
from app.agents import memory as memory_agent
from app.agents import validator as validator_agent
from app.agents import synthesizer as synthesizer_agent


def build_graph():
    if Graph is None:
        return None

    g = Graph(name="agentic_rag")

    # Add planner node
    try:
        planner_node = g.add_task("planner", func=planner_agent.plan)
    except Exception:
        # Fallback generic registration
        planner_node = g.add_node("planner", runner=planner_agent.plan)

    # Parallel group: retrieval, tools, memory
    try:
        retrieval_node = g.add_task("retrieval", func=retrieval_agent.retrieve)
        tools_node = g.add_task("tools", func=tool_agent.run_tools)
        memory_node = g.add_task("memory", func=memory_agent.fetch_memory)
    except Exception:
        retrieval_node = g.add_node("retrieval", runner=retrieval_agent.retrieve)
        tools_node = g.add_node("tools", runner=tool_agent.run_tools)
        memory_node = g.add_node("memory", runner=memory_agent.fetch_memory)

    # Validator and synthesizer
    try:
        validator_node = g.add_task("validator", func=validator_agent.validate)
        synth_node = g.add_task("synthesizer", func=synthesizer_agent.stream_synthesize)
    except Exception:
        validator_node = g.add_node("validator", runner=validator_agent.validate)
        synth_node = g.add_node("synthesizer", runner=synthesizer_agent.stream_synthesize)

    # Wire edges: planner -> parallel(retrieval, tools, memory)
    try:
        g.add_edge(planner_node, [retrieval_node, tools_node, memory_node], mode="parallel")
    except Exception:
        # Best-effort: serial edges if parallel API not available
        g.add_edge(planner_node, retrieval_node)
        g.add_edge(planner_node, tools_node)
        g.add_edge(planner_node, memory_node)

    # Conditional: if planner output requires_validation -> validator -> synthesizer
    # else directly to synthesizer. We express this by adding both edges and letting
    # the planner's task-level routing decide which to execute at runtime.
    try:
        g.add_edge([retrieval_node, tools_node, memory_node], validator_node)
        g.add_edge([retrieval_node, tools_node, memory_node], synth_node)
    except Exception:
        g.add_edge(retrieval_node, validator_node)
        g.add_edge(retrieval_node, synth_node)

    return g
