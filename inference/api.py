"""
inference/api.py — HTTP layer for DocuAI.

Lives next to graph.py so `from graph import app` and graph.py's own
`from parser.parser import ...` / `from query.query import ...` resolve
the same way they do when you run inference.py directly.

IMPORTANT — how to launch this (from the PROJECT ROOT, i.e. DOCUAI/, not
from inside inference/):

    uvicorn api:app --reload --port 8000 --app-dir inference

Why --app-dir and not just `cd inference && uvicorn api:app`:
- graph.py's imports (`from parser.parser import ...`) need inference/ on
  sys.path -> --app-dir inference does that.
- parser.py's file paths (`./database/docuAI/...`) are relative to the
  process's CURRENT WORKING DIRECTORY, which needs to stay DOCUAI/ (the
  project root) to match your existing folder layout (database/, docuAI/
  sit next to inference/, not inside it).
- --app-dir only touches sys.path, not cwd, so both constraints are
  satisfied at once.

Endpoints:
    POST /api/documents/upload   — upload a file, parse it, write to Neo4j
    GET  /api/documents          — list documents parsed this server session
    POST /api/ask                — ask a question against a parsed document
    GET  /api/pages/{doc}/{n}    — serve a page image
"""

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from graph import app as docuai_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docuai.api")

app = FastAPI(title="DocuAI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Relative to cwd (project root, DOCUAI/), same convention as your
# database/docuAI/... paths.
UPLOAD_DIR = Path("./docuAI/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory session registry: document_name -> {thread_id, image_folder, pages}
# Rebuilt on server restart. Neo4j data itself is untouched by a restart —
# you'd just need to re-parse to rebuild this in-memory index.
DOCUMENTS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Upload + parse
# ---------------------------------------------------------------------------
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), document_name: Optional[str] = Form(None)):
    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"Parsing {dest} (thread {thread_id})")
    try:
        result = docuai_graph.invoke({"file_path": str(dest), "document_name": document_name}, config=config)
    except Exception as e:
        logger.exception("Parse failed")
        raise HTTPException(status_code=500, detail=str(e))

    metadata = result.get("metadata")
    if not metadata:
        raise HTTPException(status_code=422, detail="Parsing produced no pages — check server logs.")

    doc_name = result["document_name"]
    DOCUMENTS[doc_name] = {
        "thread_id": thread_id,
        "image_folder": result["image_folder"],
        "pages": metadata,
    }

    return {
        "document_name": doc_name,
        "page_count": len(metadata),
        "pages": [
            {"page_no": p["page_no"], "description": p["description"], "reference": p["reference"]}
            for p in metadata
        ],
    }


@app.get("/api/documents")
async def list_documents():
    return [
        {"document_name": name, "page_count": len(info["pages"])}
        for name, info in DOCUMENTS.items()
    ]


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    document_name: str
    question: str


@app.post("/api/ask")
async def ask(req: AskRequest):
    info = DOCUMENTS.get(req.document_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unknown document '{req.document_name}'. Upload it first.")

    config = {"configurable": {"thread_id": info["thread_id"]}}
    try:
        result = docuai_graph.invoke({"question": req.question}, config=config)
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))

    return result["answer"]


# ---------------------------------------------------------------------------
# Page images
# ---------------------------------------------------------------------------
@app.get("/api/pages/{document_name}/{page_no}")
async def get_page_image(document_name: str, page_no: int):
    info = DOCUMENTS.get(document_name)
    if not info:
        raise HTTPException(status_code=404, detail="Unknown document")

    image_folder = Path(info["image_folder"])
    candidates = list(image_folder.glob("page_*.png"))
    matches = [c for c in candidates if int(c.stem.replace("page_", "")) == page_no]

    if not matches:
        raise HTTPException(status_code=404, detail=f"Page {page_no} image not found in {image_folder}")

    return FileResponse(matches[0])


# ---------------------------------------------------------------------------
# NOTE: this backend is API-only now. The React app (Vite dev server on
# port 5173) is what you open in the browser — it proxies /api/* calls
# here automatically (see frontend/vite.config.js). This process just
# needs to keep running in its own terminal alongside `npm run dev`.
# ---------------------------------------------------------------------------
