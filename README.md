# AI Site Engineer — Construction Intelligence Copilot

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.4-black.svg)](https://nextjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E.svg)](https://supabase.com)
[![IS Codes](https://img.shields.io/badge/Standard-IS%20456%20%7C%20SP%2034-00E5FF.svg)](docs/architecture.md)
[![Tests](https://img.shields.io/badge/Tests-26%20Passed-brightgreen.svg)](backend/tests)
[![CI Pipeline](https://github.com/ShahzebKhan17/AI-Site-Engineer/actions/workflows/ci.yml/badge.svg)](https://github.com/ShahzebKhan17/AI-Site-Engineer/actions)

> **Verifiable, Zero-Arithmetic-Hallucination AI for Civil Site Engineers & Construction Contractors.**  
> Built with Hybrid RAG (`pgvector` + `tsvector`), FastAPI, Next.js, and a deterministic civil engineering Bar Bending Schedule (BBS) engine.

---

## The Problem & The Architectural Innovation

In civil construction, a single arithmetic error or hallucinated lapping dimension in a high-rise column can lead to structural failure or hundreds of thousands of dollars in wasted rebar steel.

General-purpose Large Language Models (LLMs) hallucinate arithmetic, confuse similar structural member IDs (`C11` vs `C12`), and cannot be audited for structural compliance.

### The Neuro-Symbolic Solution:
1. **Probabilistic Layer (RAG & Extractor):**
   * Digital PDF text extraction with page citations.
   * **Hybrid Retrieval:** Blends vector similarity ($0.55$), PostgreSQL full-text rank ($0.45$), and exact member identifier boosting ($+0.25$ for tags like `C12`).
   * **Structured Extractor:** Extracts explicit dimensions (`bar_diameter_mm`, `storey_height_mm`, `concrete_grade`, `steel_grade`) without performing any calculations.
2. **Deterministic Layer (Python Engineering Engine):**
   * Implements the **Bureau of Indian Standards (BIS)** building code rules:
     * **IS 456:2000 Clause 26.2.1:** Design bond stress ($\tau_{bd}$) and development length ($L_d = \frac{\phi \cdot 0.87 f_y}{4 \tau_{bd}}$).
     * **IS 456:2000 Clause 26.2.5.1:** Compression/tension column lap lengths and stagger spacing.
     * **SP 34:1987 Clause 3.2 & IS 2502:** Standard elongation bend deductions ($-2d$ for $90^\circ$ bends).
     * **SP 34:1987 Clause 7.2:** Column confinement lap zones ($H/2$ central clear height).
   * Generates step-by-step Bar Bending Schedules (BBS) and computes total steel tonnage using $\text{Weight} = \frac{d^2}{162}\text{ kg/m}$.

---

## Technical Architecture

```text
PDF Structural Drawings ──> Text Extraction & Chunks ──> 1536-dim Embeddings
                                                                 │
                                                                 ▼
Engineer Query ("Cutting length for C12?") ──────────> Supabase Hybrid RPC
                                                                 │
                                                                 ▼
Deterministic Python Engine <── Validated Inputs <── Ranked Evidence Chunks
            │
            ▼
Bar Bending Schedule (BBS) + Verification Modal + CSV Export
```

For complete mathematical derivations and Mermaid diagrams, see [docs/architecture.md](docs/architecture.md).

---

## Repository Structure

```text
AI-Site-Engineer/
├── backend/
│   ├── app/
│   │   ├── engineering/
│   │   │   ├── calculators/column.py      # Deterministic longitudinal bar calculator
│   │   │   ├── rules/is456.py             # IS 456:2000 bond stress & Ld formulas
│   │   │   ├── rules/sp34.py              # SP 34 bend allowances & lap zones
│   │   │   └── models.py                  # Pydantic v2 engineering data schemas
│   │   ├── ingestion/
│   │   │   ├── pdf.py                     # Word-boundary text chunker & entity tagger
│   │   │   └── models.py                  # Extracted chunk models
│   │   ├── rag/
│   │   │   ├── embeddings.py              # 1536-dim vector generator (pgvector)
│   │   │   ├── extractor.py               # Structured drawing dimension parser
│   │   │   ├── orchestrator.py            # End-to-end question-to-BBS coordinator
│   │   │   ├── question_parser.py         # Regex structural intent analyzer
│   │   │   ├── retrieval.py               # Hybrid search ranking engine
│   │   │   └── supabase_client.py         # Supabase PostgREST & RPC client
│   │   ├── routers/                       # FastAPI route handlers
│   │   └── main.py                        # FastAPI entrypoint with CORS
│   ├── tests/
│   │   ├── fixtures/sample_drawings.py    # Multi-page binary PDF drawing generator
│   │   ├── test_column_calculator.py
│   │   ├── test_end_to_end_drawing_workflow.py
│   │   ├── test_extractor.py
│   │   ├── test_hybrid_retrieval.py
│   │   ├── test_is456_rules.py
│   │   ├── test_orchestrator.py
│   │   ├── test_pdf_ingestion.py
│   │   ├── test_question_parser.py
│   │   └── test_rag_embeddings.py
│   └── requirements.txt
├── src/
│   └── app/
│       ├── globals.css                    # Dark blueprint technical design system
│       ├── layout.tsx                     # Root HTML & metadata
│       └── page.tsx                       # Interactive Engineering Workspace UI
├── supabase/
│   └── migrations/
│       ├── 202610120001_initial_schema.sql    # Drawings, chunks, and pgvector schema
│       └── 202610120002_hybrid_retrieval.sql   # hybrid_search_document_chunks SQL RPC
├── docs/
│   └── architecture.md                    # In-depth technical specifications
├── package.json
└── tsconfig.json
```

---

## Quickstart & Installation

### 1. Backend Service (FastAPI)

```bash
# Navigate to backend
cd backend

# Install dependencies
pip install -r requirements.txt

# Run automated test suite (23 passing tests)
python -m pytest tests

# Start FastAPI dev server (port 8000)
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Application (Next.js)

```bash
# In the root project directory
npm install

# Build production bundle
npm run build

# Start local Next.js dev server (port 3000)
npm run dev
```

Visit `http://localhost:3000` in your browser.

---

## Civil Engineering Calculation Walkthrough (Column C12)

| Component / Provision | Rule / IS Code Standard | Length (mm) |
|---|---|---|
| **Storey Height** | Architectural Elevation | `+3000.0` |
| **Footing Embedment** | Foundation Drawing Detail | `+500.0` |
| **Footing $90^\circ$ Bend Leg** | SP 34:1987 Cl. 3.3 ($\ge 300\text{ mm}$ or $16d$) | `+300.0` |
| **Compression Lap Length** | IS 456 Cl. 26.2.5.1 ($\max(L_d, 24d) = 38.84d$) | `+621.4` |
| **$90^\circ$ Elongation Bend Deduction** | SP 34 Cl. 3.2 & IS 2502 ($-2d$) | `-32.0` |
| **TOTAL CUTTING LENGTH** | **Deterministic Sum** | **$4389.4\text{ mm}$ ($4.389\text{ m}$)** |

Total steel weight for 4 bars:
$$\text{Weight} = \frac{16^2}{162} \times 4.389 \times 4 \approx 27.74\text{ kg}$$

---

## License

MIT © 2026 Shahzeb Khan. Built for civil site engineers, contractors, and structural consultants.
