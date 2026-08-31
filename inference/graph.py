"""
graph.py — LangGraph orchestrator for DocuAI

Maps to the "Agentic Orchestrator (Multi-Agent Dispatcher)" box in your
architecture diagram: it looks at the incoming state and decides whether
to send it to Agent 1 (parser) or Agent 2 (query).

    START -> router -> parse_node -> router -> query_node -> END
                    (or straight to query_node if metadata already exists)

- If state has a file_path but no metadata yet -> goes to parse_node.
- After parsing, if a question is also present -> falls through to query_node.
- If state already has metadata and a question -> goes straight to query_node.

State is persisted across calls via a checkpointer (thread_id), so you can
parse a document once, then ask multiple questions against it without
re-parsing every time.
"""

import logging
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from parser.parser import parse_document
from query.query import answer_query

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared state passed between nodes
# ---------------------------------------------------------------------------
class DocuAIState(TypedDict, total=False):
    file_path: Optional[str]        # set this to trigger parsing
    question: Optional[str]         # set this to trigger a query
    document_name: Optional[str]
    image_folder: Optional[str]
    metadata: Optional[list]        # all_pages, produced by parse_node
    answer: Optional[dict]          # produced by query_node


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def parse_node(state: DocuAIState) -> DocuAIState:
    logger.info(f"[parse_node] parsing {state['file_path']}")

    metadata = parse_document(state["file_path"], document_name=state.get("document_name"))
    document_name = state.get("document_name") or Path(state["file_path"]).stem
    image_folder = f"./database/docuAI/phase_01/step_02/{document_name}"

    return {
        "metadata": metadata,
        "document_name": document_name,
        "image_folder": image_folder,
    }


def query_node(state: DocuAIState) -> DocuAIState:
    logger.info(f"[query_node] answering: {state['question']}")

    answer = answer_query(
        state["question"],
        state["metadata"],
        image_folder=state["image_folder"],
    )
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Router — same job as the Agno "Agentic Orchestrator" box
# ---------------------------------------------------------------------------
def route_from_start(state: DocuAIState) -> str:
    if state.get("file_path") and not state.get("metadata"):
        return "parse"
    if state.get("question") and state.get("metadata"):
        return "query"
    return END


def route_after_parse(state: DocuAIState) -> str:
    if state.get("question"):
        return "query"
    return END


# ---------------------------------------------------------------------------
# Build + compile the graph
# ---------------------------------------------------------------------------
def build_graph():
    graph = StateGraph(DocuAIState)

    graph.add_node("parse", parse_node)
    graph.add_node("query", query_node)

    graph.add_conditional_edges(START, route_from_start, {"parse": "parse", "query": "query", END: END})
    graph.add_conditional_edges("parse", route_after_parse, {"query": "query", END: END})
    graph.add_edge("query", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


app = build_graph()


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "stress-dossier-demo"}}

    # Turn 1: parse the document
    result = app.invoke(
        {"file_path": "./warehouse/docuAI/Stress-Dossier_Synthetic-Data.pdf"},
        config=config,
    )
    print("parsed pages:", len(result.get("metadata") or []))

    # Turn 2: ask a question — reuses the same thread_id, so metadata
    # from turn 1 is already in state, no re-parsing needed.
    result = app.invoke(
        {"question": "What is the stress limit?"},
        config=config,
    )
    print(result["answer"])
