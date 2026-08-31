"""
parser.py — Agent 1: Parser

Ingestion pipeline: normalize any input file to PDF, split into page images,
extract structured metadata per page with a vision LLM, and write the
result into Neo4j.

Entry point for the agentic framework: parse_document(file_path)
"""

import io
import re
import json
import time
import base64
import shutil
import logging
import subprocess
from pathlib import Path

import requests
from PIL import Image

from config import INVOKE_URL, HEADER_AUTH, get_driver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
METADATA_EXTRACTION_PROMPT = """
task: analyze this document page image and extract structured metadata.

instruction:
- respond with ONLY raw json, no intro, no outro, no markdown code block
- transcribe exact codes, reference numbers, dates, and titles VERBATIM as they appear on the page (do not paraphrase numbers/codes)
- describe every element on the page: titles, tables (with column names), signatures, headers, footers
- if a value is unreadable, write "unclear" rather than guessing

output format (single json object, not a list):
{
  "description": "<exhaustive description of every element on the page, including exact titles and table structure>",
  "reference": "<all exact reference codes, document numbers, dates, issue numbers found on the page, verbatim>"
}
"""

REFERENCE_SYSTEM_PROMPT = """
You are given a document represented as multiple pages.

Return ONLY valid JSON.
Do NOT return markdown.
Do NOT explain anything.

Output Schema:

{
  "pages": [
    {"page_no": 1, "description": "...", "reference": "..."}
  ],
  "references": [
    {"from_page": 2, "to_page": 5, "reference_contains": "..."}
  ]
}

Instructions:
1. Copy every page exactly as provided into the "pages" array.
2. Compare EVERY page against EVERY other page.
3. Determine whether a page references another page using BOTH description and reference.
4. A reference may be a table, figure, section, heading, topic, procedure, semantic description, or document element.
5. Match semantically, not only exact words.
6. Never invent page numbers. Never create self references.
7. Multiple references from one page are allowed.
8. If no reference exists, return "references": [].

Return ONLY JSON.
"""


# ---------------------------------------------------------------------------
# Stage 1 — Normalize any input file to PDF
# ---------------------------------------------------------------------------
def convert_to_pdf(path):
    """
    Converts docx/xlsx/html/md/csv/pdf -> PDF using LibreOffice headless.
    Returns the output PDF path on success, or None on failure.
    """
    try:
        input_path = Path(path).expanduser().resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_dir = Path("./database/docuAI")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_pdf = output_dir / (input_path.stem + ".pdf")

        if input_path.suffix.lower() == ".pdf":
            shutil.copy2(str(input_path), str(output_pdf))
        else:
            convert_cmd = [
                "soffice", "--headless", "--convert-to", "pdf",
                "--outdir", str(output_dir), str(input_path)
            ]
            if shutil.which("soffice") is None:
                if shutil.which("libreoffice"):
                    convert_cmd[0] = "libreoffice"
                else:
                    raise EnvironmentError("LibreOffice (soffice) not found in PATH.")

            result = subprocess.run(convert_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Conversion failed: {result.stderr}")

            if not output_pdf.is_file():
                raise FileNotFoundError("Converted PDF not found after LibreOffice run.")

        if input_path.stat().st_size == 0:
            logger.warning(f"{input_path.name} is empty — produced an empty PDF.")

        logger.info(f"Converted {input_path.name} -> {output_pdf}")
        return output_pdf

    except Exception as e:
        logger.error(f"convert_to_pdf failed for {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Stage 2 — Split PDF into page images
# ---------------------------------------------------------------------------
def extract_page_images(pdf_path, output_dir=None):
    """
    Runs Docling layout extraction on one PDF and saves one PNG per page.
    Returns the folder the images were written to.
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    from docling_core.types.doc.document import DoclingDocument, ContentLayer
    from docling_core.types.doc import SectionHeaderItem, TextItem, TableItem, PictureItem
    from docling_core.transforms.visualizer.layout_visualizer import LayoutVisualizer

    pdf_path = Path(pdf_path)
    if output_dir is None:
        output_dir = Path("./database/docuAI/phase_01/step_02") / pdf_path.stem
    output_dir = Path(output_dir)

    pipeline_options = PdfPipelineOptions(generate_page_images=True, images_scale=1.0)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})
    visualizer = LayoutVisualizer()
    visualizer.params.show_label = False

    result = converter.convert(str(pdf_path))
    doc = result.document

    filtered_doc = DoclingDocument(name=f"{doc.name}_level1")
    for page_no, page_item in doc.pages.items():
        filtered_doc.pages[page_no] = page_item

    for item, level in doc.iterate_items(included_content_layers={ContentLayer.BODY}):
        if level != 1:
            continue
        prov = item.prov[0] if getattr(item, "prov", None) else None
        if isinstance(item, SectionHeaderItem):
            filtered_doc.add_heading(text=item.text, level=item.level, prov=prov)
        elif isinstance(item, TableItem):
            filtered_doc.add_table(data=item.data, prov=prov)
        elif isinstance(item, PictureItem):
            filtered_doc.add_picture(prov=prov)
        elif isinstance(item, TextItem):
            filtered_doc.add_text(label=item.label, text=item.text, prov=prov)

    images = visualizer.get_visualization(doc=filtered_doc)
    for page_num, pil_image in images.items():
        out_path = output_dir / f"page_{page_num:0{len(str(len(images)))}d}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pil_image.save(out_path)

    logger.info(f"Extracted {len(images)} page images to {output_dir}")
    return output_dir


# ---------------------------------------------------------------------------
# Stage 3 — VLM metadata extraction per page image
# ---------------------------------------------------------------------------
def encode_image_for_budget(image_path, max_b64_chars=150000, max_dim=1600):
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


def _call_vision_inference(image_b64, prompt_text, retries=3):
    payload = {
        "model": "meta/llama-3.2-11b-vision-instruct",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }],
        "max_tokens": 500,
        "temperature": 0.44,
        "top_p": 0.44,
        "stream": False
    }
    headers = {"Authorization": HEADER_AUTH, "Content-Type": "application/json", "Accept": "application/json"}

    for attempt in range(retries):
        try:
            resp = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=(10, 45))

            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait}s")
                time.sleep(wait)
                continue

            if resp.status_code in (401, 403):
                # Auth problems won't fix themselves on retry -- fail fast and
                # print the body so it's obvious it's a key/header issue.
                logger.error(f"Auth error {resp.status_code}: {resp.text[:500]}")
                return resp

            if resp.status_code >= 500:
                # A 500 that returns almost instantly (sub-second) is usually
                # a malformed request/header, not real server load -- log the
                # body so you can actually see which.
                logger.warning(
                    f"Server error {resp.status_code} on attempt {attempt + 1}: {resp.text[:500]}"
                )
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return resp

            return resp

        except requests.exceptions.ReadTimeout:
            wait = 5 * (attempt + 1)
            logger.warning(f"Vision inference read timeout, retrying in {wait}s")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            # Catches ConnectionError, ChunkedEncodingError, SSLError, etc. so
            # a network blip doesn't take down the whole pipeline run.
            wait = 5 * (attempt + 1)
            logger.warning(f"Request failed ({e.__class__.__name__}: {e}), retrying in {wait}s")
            time.sleep(wait)
    return None


def preflight_check():
    """
    Fires one cheap text-only request before touching any pages. Fails loudly
    and immediately if the API key/header/endpoint is broken, instead of
    discovering it only after burning through every page of the document.
    Returns True/False.
    """
    headers = {"Authorization": HEADER_AUTH, "Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "model": "meta/llama-3.2-11b-vision-instruct",
        "messages": [{"role": "user", "content": "reply with just: ok"}],
        "max_tokens": 1500,
        "stream": False
    }
    try:
        resp = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=(10, 30))
    except requests.exceptions.RequestException as e:
        logger.error(f"Preflight check could not reach {INVOKE_URL}: {e}")
        return False

    if resp.status_code != 200:
        logger.error(f"Preflight check failed: HTTP {resp.status_code}: {resp.text[:500]}")
        return False

    logger.info("Preflight check passed — API key and endpoint are working.")
    return True


def extract_page_metadata(image_dir, doc_file_name):
    """
    Runs VLM extraction over every page_*.png in image_dir.
    Returns all_pages = [{file_name, page_no, description, reference}, ...]
    """
    all_pages = []
    image_dir = Path(image_dir)
    png_files = sorted([f for f in image_dir.iterdir() if f.suffix == ".png"])
    logger.info(f"Found {len(png_files)} pages in {image_dir}")

    for i, image_path in enumerate(png_files, 1):
        page_number = int(image_path.stem.replace("page_", ""))
        logger.info(f"[{i}/{len(png_files)}] {image_path.name}")

        image_b64 = encode_image_for_budget(image_path)
        resp = _call_vision_inference(image_b64, METADATA_EXTRACTION_PROMPT)

        if resp is None:
            logger.error(f"Page {page_number}: gave up after retries")
            continue
        if resp.status_code != 200:
            logger.error(f"Page {page_number}: HTTP {resp.status_code}: {resp.text[:500]}")
            continue

        try:
            raw_content = resp.json()["choices"][0]["message"]["content"]
            print("\n========== RAW MODEL OUTPUT ==========")
            print(raw_content)
            print("======================================\n")

            # Clean response
            raw_content = raw_content.strip()

            if raw_content.startswith("```"):
                raw_content = raw_content.replace("```json", "")
                raw_content = raw_content.replace("```", "")
                raw_content = raw_content.strip()

            # Keep only JSON object
            start = raw_content.find("{")
            end = raw_content.rfind("}")

            if start != -1 and end != -1:
                raw_content = raw_content[start:end + 1]

            description = raw_content

            reference = ""

            patterns = [
                r"Reference:\s*(.*)",
                r"Reference Number:\s*(.*)",
                r"Document Number:\s*(.*)"
            ]

            for pattern in patterns:
                m = re.search(pattern, raw_content, re.IGNORECASE)
                if m:
                    reference = m.group(1).strip()
                    break

            page_data = {
                "description": description,
                "reference": reference
            }
            all_pages.append({
                "file_name": doc_file_name,
                "page_no": page_number,
                "description": page_data.get("description", ""),
                "reference": page_data.get("reference", "")
            })
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Page {page_number}: bad response ({e})")
            continue

    logger.info(f"Extracted metadata for {len(all_pages)}/{len(png_files)} pages")
    return all_pages


# ---------------------------------------------------------------------------
# Stage 4 — Find cross-page references + write everything to Neo4j
# ---------------------------------------------------------------------------
def write_pages_to_graph(driver, all_pages, document_name):
    """
    Sends all_pages to a text LLM to find REFERENCES between pages,
    then writes (Document)-[:HAS_PAGE]->(Page)-[:REFERENCES]->(Page) into Neo4j.
    Returns 0 = success, -1 = failure.
    """
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": REFERENCE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"document_name": document_name, "pages": all_pages}, indent=2)}
        ],
        "temperature": 0.1,
        "top_p": 0.9,
        "max_tokens": 8192,
        "stream": False
    }
    headers = {"Authorization": HEADER_AUTH, "Accept": "application/json"}

    response = requests.post(INVOKE_URL, headers=headers, json=payload)
    if response.status_code != 200:
        logger.error(f"Reference API error {response.status_code}: {response.text[:300]}")
        return -1

    response = response.json()
    if "choices" not in response:
        logger.error("No response from model.")
        return -1

    content = response["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(content)
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return -1

    pages = data.get("pages", [])
    references = data.get("references", [])
    logger.info(f"Writing {len(pages)} pages, {len(references)} references to graph")

    with driver.session() as session:
        session.run("MERGE (d:Document {document_name:$document_name})", document_name=document_name)

        for p in pages:
            session.run(
                """
                MATCH (d:Document {document_name:$document_name})
                MERGE (pg:Page {page_no:$page_no, document_name:$document_name})
                SET pg.name = "Page " + toString($page_no),
                    pg.description = $description,
                    pg.reference = $reference
                MERGE (d)-[:HAS_PAGE]->(pg)
                """,
                document_name=document_name,
                page_no=p["page_no"],
                description=p.get("description", ""),
                reference=p.get("reference", "")
            )

        for r in references:
            session.run(
                """
                MATCH (a:Page {page_no:$from_page, document_name:$document_name})
                MATCH (b:Page {page_no:$to_page, document_name:$document_name})
                MERGE (a)-[rel:REFERENCES]->(b)
                SET rel.reference_contains=$reference_contains
                """,
                document_name=document_name,
                from_page=r["from_page"],
                to_page=r["to_page"],
                reference_contains=r.get("reference_contains", "")
            )

    logger.info("Graph write complete")
    return 0


# ---------------------------------------------------------------------------
# Master function — this is the only thing the agentic framework should call
# ---------------------------------------------------------------------------
def parse_document(file_path, document_name=None):
    """
    End-to-end: any file -> PDF -> page images -> VLM metadata -> Neo4j graph.
    Returns all_pages metadata (also the exact input answer_query() needs).
    """
    if not preflight_check():
        logger.error("parse_document aborted: preflight check failed (see error above — "
                     "check NVIDIA_API_KEY in your .env for stray quotes/whitespace, "
                     "and confirm the key is active at build.nvidia.com)")
        return None

    pdf_path = convert_to_pdf(file_path)
    if pdf_path is None:
        logger.error(f"parse_document aborted: conversion failed for {file_path}")
        return None

    document_name = document_name or pdf_path.stem
    image_dir = extract_page_images(pdf_path)
    metadata = extract_page_metadata(image_dir, document_name)

    driver = get_driver()
    try:
        write_pages_to_graph(driver, metadata, document_name)
    finally:
        driver.close()

    return metadata


if __name__ == "__main__":
    parse_document("./warehouse/docuAI/Stress-Dossier_Synthetic-Data.pdf")