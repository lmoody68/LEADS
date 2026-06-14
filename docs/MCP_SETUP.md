# Connect L.E.A.D.S. as an MCP server

`backend/mcp_server.py` exposes the local L.E.A.D.S. app as **MCP tools**, so an
MCP client (Claude Desktop, Claude Code, etc.) can drive the app directly — ask
cited legal questions, write memos, transcribe jargon, brief a case, run the
compliance advisor, check a citation, classify text, discover datasets, and grow
the corpus.

## Tools exposed

| Tool | What it does |
|------|--------------|
| `leads_health` | App health + capabilities (providers, corpus size, cache, classifier) |
| `leads_ask` | Citation-grounded answer over statutes + live case law |
| `leads_research_memo` | Structured agentic IRAC memo with citations |
| `leads_explain_plain` | Transcribe jargon / a case into plain English |
| `leads_case_brief` | IRAC case brief (facts/issue/rule/analysis/holding) |
| `leads_compliance` | Permissible-purpose analysis (FCRA/FDCPA/DPPA/GLBA) |
| `leads_citator` | Validate a citation + cited-by + recent citing cases |
| `leads_classify` | Predict a passage's document type |
| `leads_classifier_status` | Classifier metrics |
| `leads_discover_datasets` | Discover public legal datasets (HF + Kaggle) |
| `leads_corpus_status` | Corpus size + source breakdown |
| `leads_ingest` | Grow the corpus from an official public API |

## Prerequisites

1. **Start the backend** (the MCP server is a thin wrapper over its REST API):
   ```powershell
   cd C:\Users\lesli\Documents\LEADS\backend
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```
2. The MCP server talks to `http://127.0.0.1:8000/api` by default. Override with
   the `LEADS_API_URL` env var if needed.

## Register with Claude Desktop

Edit `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`) and add:

```json
{
  "mcpServers": {
    "leads": {
      "command": "C:\\Users\\lesli\\Documents\\LEADS\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\lesli\\Documents\\LEADS\\backend\\mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. You'll see the `leads` tools available. (Keep the backend
running while you use them.)

## Register with Claude Code

From the repo root:

```powershell
claude mcp add leads -- C:\Users\lesli\Documents\LEADS\backend\.venv\Scripts\python.exe C:\Users\lesli\Documents\LEADS\backend\mcp_server.py
```

Or add a `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "leads": {
      "command": "C:\\Users\\lesli\\Documents\\LEADS\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\lesli\\Documents\\LEADS\\backend\\mcp_server.py"]
    }
  }
}
```

## Try it (once connected)

- "Use **leads_ask**: *When may a debt collector contact a third party?*"
- "Run **leads_compliance** on: *A landlord wants to pull a tenant's credit report.*"
- "**leads_citator** for *Heintz v. Jenkins, 514 U.S. 291*."
- "**leads_case_brief** for *Gideon v. Wainwright, 372 U.S. 335*."
- "**leads_ingest** courtlistener *FDCPA attorney debt collection*."

All guardrails are inherited from the app: public legal data only, no scraping,
no PII — general legal information, not legal advice.
