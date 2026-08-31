"""
config.py — shared setup for DocuAI (parser.py + query.py both import from here)

Source: cell 0 (client init only, NOT the code-generation prompt),
        cell 9 (env var loading, NOT the print statements)
"""

import os
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# Logging — parser.py and query.py both just do: logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ---------------------------------------------------------------------------
# Env vars
# ---------------------------------------------------------------------------
def _clean_env(value):
    """Strip whitespace and accidental wrapping quotes (a common .env footgun:
    NVIDIA_API_KEY="nvapi-xxx" gets loaded literally as '"nvapi-xxx"', which
    breaks the Authorization header and NVIDIA's gateway returns a fast 500
    instead of a clean 401)."""
    if value is None:
        return value
    return value.strip().strip('"').strip("'")

NVIDIA_API_KEY = _clean_env(os.getenv("NVIDIA_API_KEY"))
NEO4J_URI = _clean_env(os.getenv("NEO4J_URI"))
NEO4J_USER = _clean_env(os.getenv("NEO4J_USER"))
NEO4J_PASSWORD = _clean_env(os.getenv("NEO4J_PASSWORD"))

if not NVIDIA_API_KEY:
    raise RuntimeError("NVIDIA_API_KEY not set")
if not NVIDIA_API_KEY.startswith("nvapi-"):
    logging.getLogger(__name__).warning(
        "NVIDIA_API_KEY doesn't start with 'nvapi-' — check your .env for stray "
        "quotes, extra spaces, or a copy-paste error."
    )

# ---------------------------------------------------------------------------
# NVIDIA — raw REST constants (used by parser.py / query.py via `requests`,
# matches how cells 6, 7, 10, 11 actually call the API)
# ---------------------------------------------------------------------------
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
HEADER_AUTH = f"Bearer {NVIDIA_API_KEY}"

# ---------------------------------------------------------------------------
# NVIDIA — OpenAI-style client (from cell 0). Not currently used by the
# pipeline, but kept here in case you want client.chat.completions.create(...)
# style calls somewhere instead of raw requests.
# ---------------------------------------------------------------------------
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)


# ---------------------------------------------------------------------------
# Neo4j driver factory (from cell 8, minus the debug print)
# ---------------------------------------------------------------------------
def get_driver():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    return driver