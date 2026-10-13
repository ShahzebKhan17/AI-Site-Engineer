# System Architecture & Technical Specifications

## Architectural Overview

AI Site Engineer separates probabilistic semantic information extraction from deterministic structural civil engineering computation. Structural calculations require zero hallucination, strict adherence to national building codes (IS 456:2000, SP 34:1987), and verifiable drawing page citations.

```mermaid
flowchart TD
    subgraph Ingestion ["1. Drawing Ingestion Layer"]
        PDF[PDF Structural Drawings] --> Chunking[pypdf Page-Cited Chunking]
        Chunking --> Entities[Member Entity Extractor (C12, B4, F1)]
        Entities --> Embeddings[1536-dim Embedding Generator]
        Embeddings --> SupabaseDB[(Supabase pgvector & tsvector)]
    end

    subgraph RAG ["2. Hybrid RAG Retrieval Layer"]
        UserQ[Site Engineer Question] --> IntentParser[Regex & Intent Parser]
        IntentParser --> HybridRPC[hybrid_search_document_chunks RPC]
        SupabaseDB --> HybridRPC
        HybridRPC --> Evidence[Ranked Drawing Chunks + Citations]
    end

    subgraph Extraction ["3. Structured Parameter Extractor"]
        Evidence --> LLMExtractor[Structured Parameter Extractor]
        LLMExtractor --> PydanticReq[Validated ColumnBarRequest]
    end

    subgraph Engine ["4. Deterministic Civil Engineering Engine"]
        PydanticReq --> IS456[IS 456:2000 Bond Stress & Ld Engine]
        IS456 --> SP34[SP 34:1987 Detailing & Lap Zone Rules]
        SP34 --> BBSCalc[Longitudinal Bar Calculator]
        BBSCalc --> BBSResult[ColumnBarResult & BBS Schedule]
    end

    subgraph UI ["5. Engineering Workspace UI"]
        BBSResult --> NextUI[Next.js Blueprint Workspace]
        NextUI --> QAQC[QA/QC Sign-off & BBS CSV Export]
    end
```

---

## Civil Engineering Codes & Formulas

### 1. Development Length ($L_d$) — IS 456:2000 Clause 26.2.1

$$L_d = \frac{\phi \cdot \sigma_s}{4 \tau_{bd}}$$

Where:
* $\phi$ = Nominal diameter of the bar (mm).
* $\sigma_s$ = Stress in bar at design load = $0.87 \cdot f_y$.
* $\tau_{bd}$ = Design bond stress in plain bars in tension (IS 456 Table 26.2.1.1):
  * **M20:** $1.2\text{ N/mm}^2$
  * **M25:** $1.4\text{ N/mm}^2$
  * **M30:** $1.5\text{ N/mm}^2$
  * **M35:** $1.7\text{ N/mm}^2$
  * **M40:** $1.9\text{ N/mm}^2$

#### Modifiers (Clause 26.2.1.1):
* **Deformed HYSD Bars (Fe415 / Fe500 / Fe550):** Increase $\tau_{bd}$ by **60%** ($\times 1.6$).
* **Bars in Compression:** Increase $\tau_{bd}$ by **25%** ($\times 1.25$).

---

### 2. Column Lap Lengths & Lapping Zones — IS 456 Clause 26.2.5.1 & SP 34 Clause 7.2

* **Compression Splicing:** $\text{Lap Length} = \max(L_d\text{ in compression}, 24\phi)$.
* **Tension Splicing:** $\text{Lap Length} = \max(L_d\text{ in tension}, 30\phi)$.
* **Permissible Lapping Zone:**
  * Splicing is restricted to the central half ($H_{\text{clear}} / 2$) of the clear storey height.
  * No lapping is permitted in the plastic hinge / beam-column nodal confinement zone ($\max(H_{\text{clear}}/4, 450\text{ mm})$ from beam faces).
  * Maximum 50% of column longitudinal bars may be spliced at any single cross-section.
  * Stagger distance between adjacent lap sections must be $\ge 1.3 \times \text{Lap Length}$.

---

### 3. Elongation Bend Deductions — SP 34:1987 Clause 3.2 & IS 2502

Physical stretching occurs when high-yield bars are bent. The cutting length must deduct:
* $45^\circ$ bend: $-1\phi$
* $90^\circ$ bend: $-2\phi$
* $135^\circ$ hook: $-3\phi$
* $180^\circ$ U-hook: $-4\phi$

---

### 4. Rebar Unit Weight Formula

$$\text{Unit Weight} = \frac{d^2}{162}\text{ kg/m}$$

For $16\text{ mm}$ rebar: $\frac{16^2}{162} = 1.58\text{ kg/m}$.

---

## Hybrid Search Function Specification

Defined in PostgreSQL / `pgvector` migration `202610120002_hybrid_retrieval.sql`:

$$\text{Score} = 0.45 \cdot \text{KeywordScore} + 0.55 \cdot \text{SemanticScore} + \text{EntityBoost}$$

* **KeywordScore:** Full-text rank (`ts_rank_cd`) against English `tsvector`.
* **SemanticScore:** Cosine similarity ($1 - \text{distance}$) on 1536-dimensional vector embeddings.
* **EntityBoost:** $+0.25$ / $+0.35$ boost when drawing chunks contain the exact member ID (e.g. `C12`), preventing vector search collisions between similar structural tags.
