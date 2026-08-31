"""
query.py — Agent 2: Query

Retrieval pipeline: match a user question to the right page(s) using the
page metadata already in Neo4j, then ask a vision LLM to answer grounded
on the actual page image(s).

Entry point for the agentic framework: answer_query(question, all_pages, image_folder)
"""

import io
import re
import json
import time
import base64
import logging

import requests
from PIL import Image

from config import INVOKE_URL, HEADER_AUTH, get_driver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
RETRIEVAL_PROMPT_TEMPLATE = """
task: find the most relevant page(s) for the user query, based on the page index below.

instruction:
- respond with ONLY raw json, no intro, no outro, no markdown code block
- return up to {top_k} page numbers, ordered by relevance (most relevant first)
- if nothing is relevant, return an empty list

output format:
{{"matching_pages": [<page_no>, <page_no>, ...]}}

user query: "{query}"

page index:
{index_text}
"""

ANSWER_PROMPT_TEMPLATE = """

You are answering questions about a document page.

Rules:

1. Read the ENTIRE page carefully.
2. Search every title, paragraph, table, footer and note.
3. If the answer exists, quote it exactly.
4. If the answer is inside a table, read the table.
5. Include units exactly.
6. Never guess.
7. If the answer is not present on THIS page, reply only:

NOT_FOUND

Question:
{query}

"""


def strip_json_fence(text):
    """Model sometimes wraps output in ```json ... ``` — strip it before parsing."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Step 1 — which page(s) answer this query? (text-only match)
# ---------------------------------------------------------------------------
def retrieve_matching_pages(query, all_pages, top_k=3, retries=3):
    """all_pages: list of {file_name, page_no, description, reference}."""
    index_text = "\n".join(
        f"page_no: {p['page_no']} | description: {p['description']} | reference: {p['reference']}"
        for p in all_pages
    )
    prompt = RETRIEVAL_PROMPT_TEMPLATE.format(top_k=top_k, query=query, index_text=index_text)

    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.2,
        "top_p": 0.7,
        "stream": False
    }
    headers = {"Authorization": HEADER_AUTH, "Content-Type": "application/json", "Accept": "application/json"}

    for attempt in range(retries):
        try:
            resp = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=(10, 60))
        except requests.exceptions.ReadTimeout:
            logger.warning(f"Retrieval timeout, retry {attempt + 1}/{retries}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code != 200:
            logger.error(f"Retrieval HTTP {resp.status_code}: {resp.text[:300]}")
            return []

        raw_content = resp.json()["choices"][0]["message"]["content"]
        logger.debug(f"Raw retrieval output: {raw_content[:300]}")

        try:
            parsed = json.loads(strip_json_fence(raw_content))
            return parsed.get("matching_pages", [])
        except json.JSONDecodeError:
            logger.error(f"Retrieval output not valid JSON: {raw_content[:300]}")
            return []

    return []


# ---------------------------------------------------------------------------
# Step 2 — load + compress the actual matched page image
# ---------------------------------------------------------------------------
def encode_full_page(image_path, max_b64_chars=150000, max_dim=2200):
    img = Image.open(image_path).convert("L")
    quality = 75
    dim = max_dim
    while True:
        img_resized = img.copy()
        img_resized.thumbnail((dim, dim))
        buf = io.BytesIO()
        img_resized.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        if len(b64) <= max_b64_chars:
            return b64
        if quality > 40:
            quality -= 10
        else:
            dim = int(dim * 0.85)
        if dim < 500:
            return b64


# ---------------------------------------------------------------------------
# Step 3 — ask the vision LLM to answer, grounded on the actual page image
# ---------------------------------------------------------------------------
def answer_query_from_page(
    query,
    page_no,
    image_folder,
    page_description,
    page_reference,
    retries=3
):
    import os

    # Find the correct page image
    files = [f for f in os.listdir(image_folder) if f.endswith(".png")]

    image_path = None
    for f in files:
        # Matches page_1.png, page_01.png, page_001.png, etc.
        if re.match(rf"page_0*{page_no}\.png$", f):
            image_path = os.path.join(image_folder, f)
            break

    if image_path is None:
        logger.error(f"Image for page {page_no} not found.")
        return "Image not found."

    if not os.path.exists(image_path):
        logger.error(f"Page {page_no} image not found at {image_path}")
        return f"Page {page_no} image not found."

    image_b64 = encode_full_page(image_path)
    prompt = f"""
    You are answering questions about a document page.

    Question:
    {query}

    Page description:
    {page_description}

    Reference metadata:
    {page_reference}

    Read the ENTIRE page carefully.

    Search all paragraphs, tables, figures, headers and footers.

    If the answer is present, quote it exactly.

    If it is not on this page, reply ONLY:

    NOT_FOUND
    """

    payload = {
        "model": "meta/llama-3.2-90b-vision-instruct",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }],
        "max_tokens": 800,
        "temperature": 0.3,
        "top_p": 0.7,
        "stream": False
    }
    headers = {"Authorization": HEADER_AUTH, "Content-Type": "application/json", "Accept": "application/json"}

    for attempt in range(retries):
        try:
            resp = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=(20, 300))
        except requests.exceptions.ReadTimeout:
            logger.warning(f"Answer timeout, retry {attempt + 1}/{retries}")
            time.sleep(10 * (attempt + 1))
            continue

        if resp.status_code != 200:
            logger.error(f"Answer HTTP {resp.status_code}: {resp.text[:300]}")
            return f"HTTP {resp.status_code}: {resp.text[:300]}"

        return resp.json()["choices"][0]["message"]["content"]

    return "gave up after retries"


# ---------------------------------------------------------------------------
# Master function — this is the only thing the agentic framework should call
# ---------------------------------------------------------------------------
def answer_query(question, all_pages, image_folder):
    """
    Full retrieval flow: match question -> pages, then answer grounded on
    each matched page's image.
    Returns {"query", "matched_pages", "results": [{"page_no", "answer"}, ...]}
    """
    logger.info(f"Query: {question}")
    matched_pages = retrieve_matching_pages(question, all_pages)
    logger.info(f"Matched pages: {matched_pages}")

    if not matched_pages:
        return {"query": question, "matched_pages": [], "answer": "no relevant page found"}

    results = []
    for page_no in matched_pages:
        page = next((p for p in all_pages if p["page_no"] == page_no), None)

        if page is None:
            continue

        answer = answer_query_from_page(
            query=question,
            page_no=page_no,
            image_folder=image_folder,
            page_description=page["description"],
            page_reference=page["reference"]
        )

        results.append({
            "page_no": page_no,
            "answer": answer
        })
        

    return {"query": question, "matched_pages": matched_pages, "results": results}


# ---------------------------------------------------------------------------
# OPTIONAL — graph-based helpers. Not called by answer_query() above.
# Use these if you want matched pages to also pull in pages they REFERENCE
# via Neo4j before answering.
# ---------------------------------------------------------------------------
def get_all_pages(driver, document_name=None):
    """Fetch every page's description from Neo4j (builds all_pages for answer_query)."""
    query = """
    MATCH (d:Document)-[:HAS_PAGE]->(p:Page)
    RETURN d.document_name AS file_name, p.page_no AS page_no,
           p.description AS description, p.reference AS reference
    ORDER BY p.page_no
    """
    with driver.session() as session:
        result = session.run(query)
        return [
            {
                "file_name": r["file_name"],
                "page_no": r["page_no"],
                "description": r["description"],
                "reference": r["reference"]
            }
            for r in result
        ]


def expand_with_references(driver, matches):
    """
    matches: [{"file_name": ..., "page_no": ...}, ...]
    Returns each matched page plus any pages it REFERENCES in the graph.
    """
    fetched = []
    query = """
    MATCH (d:Document)-[:HAS_PAGE]->(p:Page)
    WHERE d.document_name = $file_name AND p.page_no = $page_no
    OPTIONAL MATCH (p)-[r:REFERENCES]->(ref:Page)
    RETURN d.document_name AS file_name, p.page_no AS page_no, p.description AS description,
           collect(CASE WHEN ref IS NULL THEN NULL
                        ELSE {page_no: ref.page_no, description: ref.description, reference_contains: r.reference_contains}
                   END) AS references
    """
    with driver.session() as session:
        for match in matches:
            result = session.run(query, file_name=match["file_name"], page_no=match["page_no"])
            for record in result:
                refs = [r for r in record["references"] if r is not None]
                fetched.append({
                    "file_name": record["file_name"],
                    "page_no": record["page_no"],
                    "description": record["description"],
                    "references": refs
                })
    return fetched


if __name__ == "__main__":
    driver = get_driver()
    try:
        all_pages = get_all_pages(driver, document_name="Stress-Dossier_Synthetic-Data")
        result = answer_query(
            "what is the MTOW for MP-D450neo?",
            all_pages,
            image_folder="./database/docuAI/phase_01/step_02/Stress-Dossier_Synthetic-Data"
        )
        print(json.dumps(result, indent=2))
    finally:
        driver.close()
