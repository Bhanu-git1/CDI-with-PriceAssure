# Commercial Decision Intelligence — Multi-Source Chat Assistant

A React chat UI over a FastAPI backend that answers natural-language questions about
business data. The backend uses **Dynamic Code Execution (DCE)**: an LLM writes Python
that queries a data source, and that code runs inside a restricted sandbox.

Three data sources are connected, and the backend decides which one a question belongs to:

| Source id | What it holds | Query language |
|---|---|---|
| `mysql_primary` | Pharma commercial ops — leakage & claim rejections, HCP fatigue & campaigns, work details, medicine extraction, sync audit | MySQL |
| `mysql_gpo` — shown as **Memcot** | Customer-roster validation — batch upload, HIN/DEA/HRSA/USPS/COT/member validation, membership & contracts, RBAC, audit log. Also the REG, Abbott and Eisai program pipelines | MySQL (read-only) |
| `salesforce` | Salesforce CRM custom objects for doctors and their sales representatives | SOQL / SOSL |

---

## Prerequisites

1. **MySQL Server** 8.0+ (or a reachable managed instance)
2. **Python 3.10+**
3. **Node.js 18+ & npm**
4. **An LLM provider** — one of:
   - **Groq** ([API key](https://console.groq.com/keys)), default model `openai/gpt-oss-120b`
   - **Claude via AWS Bedrock** — used when `GROQ_API_KEY` is unset and AWS keys are present
   - **Claude via the Anthropic API** — used when neither of the above is set

Selection is automatic and reported by `GET /api/` in the `provider` field.

---

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows (PowerShell):  .\venv\Scripts\Activate.ps1
# macOS / Linux:         source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env      # then fill in your credentials
python -m app.main
```

On startup the backend logs which sources registered and whether each is reachable:

```
Initializing DCE workspace with 3 data source(s): mysql_primary, mysql_gpo, salesforce
  Commercial: connected
  Memcot: connected
  Salesforce: connected
```

> **Every data source needs a distinct env-var prefix.** `.env` is last-key-wins, so
> reusing `MYSQL_*` for a second database silently repoints the first one — including
> where chat transcripts are written. DB 2 uses `GPO_MYSQL_*`.

A source whose credentials are missing is skipped with a warning; the others keep working.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

---

## How questions get routed

`POST /api/chat` accepts an optional `source` field. `auto` (the default) hands the
decision to the router in [backend/app/router/source_router.py](backend/app/router/source_router.py),
which runs a four-stage cascade, cheapest first:

1. **Explicit override** — the UI's source selector, an addressed alias in the prompt
   (`"in gpo, ..."`, `"from salesforce, ..."`, `"@gpo"`), or a short follow-up turn
   inheriting the previous answer's source. Wins outright.
2. **Deterministic scoring** — keyword and table-name matches from
   [datasources.yaml](backend/app/semantic/datasources.yaml). Only table names (+10) and
   strong keywords (+6) are *decisive*; shared vocabulary like "member" or "status" (+2)
   ranks but never decides. Routes only when the winner also clears the margin.
3. **LLM tie-break** — one small classification call with a compact source catalogue
   (no schema). Cached per prompt.
4. **Abstain** — if two sources are genuinely plausible, the assistant queries *nothing*
   and asks which one you meant, offering clickable chips. Answering from the wrong
   database is worse than one extra question.

Every answer reports its source in a badge, with the routing stage, confidence and
reason on hover.

---

## Adding another data source

No Python changes are required.

1. Add credentials to `.env` under a **new prefix**, and the matching fields to
   `Settings` in [backend/app/config.py](backend/app/config.py).
2. Add a block to [backend/app/semantic/datasources.yaml](backend/app/semantic/datasources.yaml):
   connection (by env-var *name*), semantic model file, `sandbox_global`, and a `routing`
   block. Its `strong_keywords` must not overlap another source's — startup fails loudly
   if they do, since that would make routing depend on priority instead of meaning.
3. Add its semantic model YAML next to the others.

Set `enabled: false` on any source to remove it from routing, health checks and the UI.

---

## Semantic layers

Each source has one YAML model that governs table names, columns, join paths and
pre-defined SQL. The assistant is instructed never to invent a name.

- `schema_model.yaml` — DB 1. Hand-maintained.
- `gpo_schema_model.yaml` — DB 2. **Generated — do not edit by hand.** Columns, types and
  row counts come from the live schema; the business knowledge (17 domains, 24 joins,
  11 mapping rules, 21 measures) is curated in the generator:

  ```bash
  cd backend
  python -m scripts.introspect_gpo            # dump the live schema
  python -m scripts.build_gpo_semantic_model  # regenerate the YAML
  ```

  Re-run both after any schema change.
- `salesforce_semantic_layer.yaml` — Salesforce objects and relationships.

Prompts are trimmed to the tables relevant to the question. DB 2 has 70 tables, so its
model declares `domains` and the trimmer budgets the character allowance across sections
rather than truncating mid-table.

**Row counts are read live** and injected as authoritative, overriding any counts stated
in prose. This exists because DB 1's hardcoded counts had drifted badly (`Leakage_Activity`
was described as 60 rows while holding 25,323), which pushed the model toward listing rows
instead of aggregating them.

---

## Safety

- **Read-only by statement** — only `SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN` pass
  `is_sql_safe()`.
- **Read-only by server** — sources marked `read_only: true` put every connection into a
  read-only transaction, so MySQL itself rejects writes (error 1792). The regex is a best
  effort; this is the enforcement. DB 2 uses it because its tables are live and operational.
- **Sandboxed execution** — generated code runs with a restricted `__builtins__`, an
  import whitelist, and AST checks blocking `eval`/`exec`/`open`/dunder access.
- **One global per source** — `db`, `gpo`, `sf`. Only the routed source's global is
  injected, so code aimed at the wrong source raises `NameError` instead of quietly
  returning data from a different database.
- **Row cap** — 200 rows per query. When a result is capped the answer says so, rather
  than reporting the cap as the total.
- **Infrastructure tables hidden** — `dce_chat_*` are excluded from every source, so the
  assistant cannot answer a question from its own transcripts.
- **Cross-source joins are off** — no shared business key between the commercial and GPO
  domains has been confirmed. Declare a `verified: true` entry under `cross_source_links`
  to enable one.

---

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

The suite is built around two regression guarantees:

- **Routing is unchanged** for every prompt the product already ships — the previous
  two-way keyword logic is reproduced in the test and compared against the new router.
- **Prompts are unchanged** for DB 1 and Salesforce, byte-for-byte, apart from the live
  row-counts block; the test strips that block and asserts the remainder matches exactly.

Plus query-safety coverage: row-limit edge cases (trailing `LIMIT`/`OFFSET`, scalar
aggregate subqueries, `SHOW`/`DESCRIBE`), the statement whitelist, and the read-only
declarations.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/` | Status: provider, per-source health, source catalogue, LLM health |
| `GET /api/sources` | Source catalogue for the UI selector |
| `POST /api/chat` | Ask a question. Body: `message`, `history`, optional `source` |
| `GET /api/schema?source=<id>` | Live schema for one source (defaults to the primary) |
| `GET/POST/PATCH/DELETE /api/chats...` | Chat session persistence (always DB 1) |

---

## Project structure

```
backend/
├── app/
│   ├── config.py                     # Pydantic settings (all sources' credentials)
│   ├── main.py                       # FastAPI entrypoint & endpoints
│   ├── llm_service.py                # Prompt assembly + one generic execution pipeline
│   ├── datasources/
│   │   ├── base.py                   # Adapter protocol & SourceContext
│   │   ├── mysql_adapter.py          # MySQL adapter (exclusions, capabilities, counts)
│   │   ├── salesforce_adapter.py     # Salesforce adapter
│   │   └── registry.py               # Builds sources from the manifest; validates it
│   ├── router/
│   │   └── source_router.py          # Four-stage routing cascade
│   ├── semantic/
│   │   ├── datasources.yaml          # THE MANIFEST — all sources & routing vocabulary
│   │   ├── schema_model.yaml          # DB 1 semantic layer
│   │   ├── gpo_schema_model.yaml      # DB 2 semantic layer (generated)
│   │   ├── salesforce_semantic_layer.yaml
│   │   └── loader.py                 # Semantic model loading & prompt trimming
│   └── services/
│       ├── mysql_service.py          # Pooling, read-only enforcement, row limiting
│       ├── salesforce_service.py     # Salesforce client
│       ├── code_executor.py          # Sandboxed Python execution
│       └── history_service.py        # Chat persistence (DB 1)
├── scripts/
│   ├── introspect_gpo.py             # Dump DB 2's live schema
│   └── build_gpo_semantic_model.py   # Generate DB 2's semantic layer
└── tests/                            # Routing, prompt-equivalence, query-safety
frontend/src/
├── App.jsx                           # Chat shell, status, history, source selection
├── components/
│   ├── SourceSelector.jsx            # Auto / per-source picker in the prompt bar
│   ├── MessageBubble.jsx             # Answer, table, source badge, clarify chips
│   ├── DataTable.jsx  DataChart.jsx  SchemaExplorer.jsx  LoginPage.jsx
└── utils/suggestionHelper.js         # Suggested prompts per domain
```
