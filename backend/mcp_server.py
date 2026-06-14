"""
L.E.A.D.S. MCP server — exposes the local L.E.A.D.S. app as MCP tools so an
MCP client (Claude Desktop, Claude Code, etc.) can drive the app: ask cited
legal questions, generate memos, transcribe jargon to plain English, brief a
case, run the compliance advisor, check a citation, classify text, discover
public datasets, and grow the corpus.

It is a thin, stdio MCP wrapper over the running REST API (default
http://127.0.0.1:8000/api). Start the backend first:
    .venv/Scripts/python -m uvicorn app.main:app --port 8000

Then run this server (or let your MCP client launch it):
    .venv/Scripts/python mcp_server.py

Register it with your MCP client — see docs/MCP_SETUP.md.

GUARDRAILS are inherited from the app: public legal data only, no scraping/PII,
"general legal information, not legal advice."
"""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("LEADS_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

mcp = FastMCP("leads")


def _get(path: str, params: Dict[str, Any] | None = None) -> Any:
    try:
        r = httpx.get(f"{API}{path}", params=params or {}, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:300]}
        return r.json()
    except Exception as exc:
        return {"error": f"Could not reach L.E.A.D.S. API at {API} ({exc}). Is the backend running on :8000?"}


def _post(path: str, body: Dict[str, Any]) -> Any:
    try:
        r = httpx.post(f"{API}{path}", json=body, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:300]}
        return r.json()
    except Exception as exc:
        return {"error": f"Could not reach L.E.A.D.S. API at {API} ({exc}). Is the backend running on :8000?"}


@mcp.tool()
def leads_health() -> dict:
    """Health + capabilities of the local L.E.A.D.S. app (providers, corpus size, cache, classifier)."""
    return _get("/health")


@mcp.tool()
def leads_ask(question: str, deep: bool = True) -> dict:
    """
    Ask a legal question and get a citation-grounded answer over public statutes +
    (when deep=True) live court opinions. Returns the answer, the cited sources,
    conflicts, and follow-ups.
    """
    d = _post("/ask", {"question": question, "deep": deep})
    if "error" in d:
        return d
    return {
        "answer": d.get("answer"),
        "sources": [{"citation": c.get("citation"), "title": c.get("source_title")} for c in d.get("citations", [])],
        "conflicts": d.get("conflicts", []),
        "followups": d.get("followups", []),
        "provider": d.get("provider"),
    }


@mcp.tool()
def leads_research_memo(question: str, deep: bool = True) -> dict:
    """Generate a structured agentic legal research memo (IRAC-style) with inline citations. Slow (20-60s)."""
    d = _post("/memo", {"question": question, "deep": deep})
    if "error" in d:
        return d
    return {
        "memo_markdown": d.get("memo_markdown"),
        "plan": d.get("plan", []),
        "sources": [{"n": s.get("n"), "citation": s.get("citation")} for s in d.get("sources", [])],
        "reviewer_notes": d.get("reviewer_notes", []),
        "provider": d.get("provider"),
    }


@mcp.tool()
def leads_explain_plain(text: str = "", citation: str = "") -> dict:
    """Transcribe legal jargon / a case / a statute into plain English for a non-lawyer. Supply text OR a citation."""
    return _post("/explain", {"text": text or None, "citation": citation or None})


@mcp.tool()
def leads_case_brief(text: str = "", citation: str = "") -> dict:
    """Produce an IRAC case brief (facts/issue/rule/analysis/holding). Supply pasted opinion text OR a citation."""
    return _post("/brief", {"text": text or None, "citation": citation or None})


@mcp.tool()
def leads_compliance(scenario: str) -> dict:
    """
    Teaching/advisory analysis of an investigative scenario: permissible-purpose
    verdict + governing statutes (FCRA/FDCPA/DPPA/GLBA) + restrictions + risks +
    lawful alternatives. Never a how-to for unlawful conduct.
    """
    return _post("/compliance", {"scenario": scenario})


@mcp.tool()
def leads_citator(citation: str) -> dict:
    """Validate a citation against the real CourtListener citation network: is it a known case, cited-by count, recent citing cases, treatment signal."""
    return _post("/citator", {"citation": citation})


@mcp.tool()
def leads_classify(text: str) -> dict:
    """Classify a passage by document TYPE (statute/opinion/regulation/bill) using the trained auxiliary model."""
    return _post("/classifier/predict", {"text": text})


@mcp.tool()
def leads_classifier_status() -> dict:
    """Whether the auxiliary classifier is trained, and its honest metrics (held-out + cross-validated)."""
    return _get("/classifier/status")


@mcp.tool()
def leads_discover_datasets(query: str = "legal", limit: int = 10) -> dict:
    """Discover PUBLIC legal datasets (Hugging Face + Kaggle). PII datasets are flagged and refused."""
    return _get("/datasets/discover", {"q": query, "limit": limit})


@mcp.tool()
def leads_corpus_status() -> dict:
    """Corpus size + a breakdown by source (case law, statutes, regulations, dockets, etc.)."""
    return _get("/ingest/status")


@mcp.tool()
def leads_ingest(source: str, query: str, limit: int = 5) -> dict:
    """
    Grow the corpus from an official public API. source ∈ {courtlistener, govinfo,
    federalregister, ecfr, congress, regulations, openstates, recap, oyez, fbi_cde}.
    query is the search/term/bill/offense for that source (e.g. courtlistener:'FDCPA
    attorney', congress:'HR 3221 110', oyez:'2019', fbi_cde:'all'). Official APIs
    only — no scraping, no PII.
    """
    valid = {"courtlistener", "govinfo", "federalregister", "ecfr", "congress",
             "regulations", "openstates", "recap", "oyez", "fbi_cde"}
    if source not in valid:
        return {"error": f"source must be one of {sorted(valid)}"}
    return _post(f"/ingest/{source}", {"query": query, "limit": limit})


if __name__ == "__main__":
    mcp.run()
