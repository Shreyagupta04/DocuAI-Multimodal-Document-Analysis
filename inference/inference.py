"""
main.py — single entry point for the DocuAI pipeline, now running on LangGraph.

Each conversation/session gets a thread_id. Parse once, then ask as many
questions as you want against the same thread_id without re-parsing.
"""

import logging

from graph import app

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "stress-dossier-demo"}}

    # Turn 1 — ingest the document
    parse_result = app.invoke(
        {"file_path": "./warehouse/docuAI/Stress-Dossier_Synthetic-Data.pdf"},
        config=config,
    )

    if not parse_result.get("metadata"):
        logger.error("Parsing failed — nothing to query.")
    else:
        # Turn 2 — ask a question (reuses metadata already in state)
        query_result = app.invoke(
            {"question": "What is the stress limit?"},
            config=config,
        )
        print(query_result["answer"])
