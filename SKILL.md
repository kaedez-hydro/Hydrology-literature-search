---
name: hydrology-literature-search
description: Specialized literature search and reference verification for hydrology, remote sensing, and machine learning research. Use when the user needs to: (1) search for academic papers at the intersection of hydrology, remote sensing, and ML/DL, (2) convert a research idea into optimized search queries, (3) verify reference lists against Crossref metadata before journal submission, (4) clean RIS/BibTeX files, (5) find papers on flood mapping, SAR water extraction, hydrodynamic modeling, hydrological forecasting, spatial validation, explainable AI in water resources, or any hydrology–remote sensing cross-disciplinary topic. Covers journals across hydrology/water resources, remote sensing/earth observation, and CS/ML venues.
---

# Hydrology × Remote Sensing Literature Toolkit

Three integrated tools for the full reference lifecycle: query optimization → literature search → reference verification.

## Quick Start

```bash
# 1. Optimize a research idea into search queries
python scripts/optimize_query.py "SAR flood mapping with U-Net" --llm

# 2. Search with the best query
python scripts/search.py --query "SAR flood inundation U-Net semantic segmentation" --max-results 20

# 3. Before submission: verify your reference list
python scripts/verify_references.py --ris manuscript_refs.ris
```

## Tool Overview

| Tool | Script | Requires |
|------|--------|----------|
| Query Optimizer | `optimize_query.py` | LLM mode needs API key; local mode is free |
| Literature Search | `search.py` | Free (Crossref + OpenAlex, no API keys) |
| Reference Verifier | `verify_references.py` | Free (Crossref + OpenAlex) |

## 1. Query Optimizer (`optimize_query.py`)

Converts a natural-language research direction into 3–5 optimized English search queries.

```bash
# Local mode (free, rule-based synonym expansion)
python scripts/optimize_query.py "spatial cross-validation for flood susceptibility" 

# LLM mode (smarter, needs OPENAI_API_KEY)
python scripts/optimize_query.py "compound flood modeling under climate change" --llm

# Mixed Chinese–English input (auto-detected)
python scripts/optimize_query.py "SAR影像用深度学习做洪水淹没提取"
```

The optimizer understands hydrology+RS+ML terminology and maps Chinese terms to English search vocabulary automatically.

**LLM mode** uses an OpenAI-compatible API. Set env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (optional), `OPENAI_MODEL` (default: `gpt-4o-mini`). Falls back to local mode if API unavailable.

## 2. Literature Search (`search.py`)

Multi-backend search across Crossref and OpenAlex. Deduplicates by DOI, sorts by citations.

```bash
# Basic search
python scripts/search.py --query "flood inundation deep learning SAR" --max-results 20

# With filters
python scripts/search.py --query "U-Net flood segmentation" \
    --year-start 2020 --year-end 2025 \
    --journal-filter "Journal of Hydrology,Remote Sensing of Environment" \
    --min-citations 5

# Export for reference manager
python scripts/search.py --query "spatial cross-validation ecology" --export bibtex -o refs.bib
```

**Detailed search strategies and examples:** See [references/search-guide.md](references/search-guide.md).

## 3. Reference Verifier (`verify_references.py`)

Field-by-field validation of RIS reference lists against Crossref metadata.
**This is NOT just a DOI existence check.** It compares journal name, volume, issue,
pages, year, and document type for every entry.

```bash
# Full verification
python scripts/verify_references.py --ris manuscript_refs.ris

# Output: *_CLEAN.ris, *_diff.txt, *_verification.md, *_doi_list.md
```

**Detailed verification workflow:** See [references/verification-guide.md](references/verification-guide.md).

**⚠️ Critical:** A prior verification pass that only checked `doi.org/XXX` → HTTP 200
found zero errors. Field-by-field comparison revealed **61% of entries had errors**,
including 10 wrong journal names. Always use field-by-field verification before submission.

## Journal Reference

The skill covers three layers of journals — hydrology, remote sensing, and CS/ML.
Full list with ISSNs at [references/journals.md](references/journals.md).

**Quick journal filter strings:**

```bash
# Hydrology core
--journal-filter "Journal of Hydrology,Water Resources Research,HESS"

# Remote sensing
--journal-filter "Remote Sensing of Environment,ISPRS,IEEE TGRS"

# ML methods
--journal-filter "NeurIPS,ICLR,ICML,CVPR"

# Hydrology + RS cross-disciplinary
--journal-filter "Journal of Hydrology,WRR,RSE,ISPRS,IEEE TGRS,Remote Sensing"
```

## Complete Reference Workflow

```
1. optimize_query.py   → Turn idea into search queries
2. search.py           → Find papers, export BibTeX
3. Import to Zotero    → Manage citations
4. Write manuscript    → Insert citations
5. Export RIS          → From Zotero
6. verify_references.py → Find and fix metadata errors
7. *_CLEAN.ris         → Import corrected references
8. Format final list   → Submit with confidence
```

## Requirements

- Python 3.8+
- `requests` (`pip install requests`)
- Crossref + OpenAlex: free, no API keys
- LLM query optimization: needs OpenAI-compatible API key (optional)
