# Hydrology × Remote Sensing Literature Toolkit
![Workflow](assets/covers/COVER.PNG)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)

Three integrated CLI tools covering the full academic reference lifecycle for hydrology–remote sensing–machine learning research:

| Tool | Script | What it does |
|------|--------|---------------|
| 🔍 **Query Optimizer** | `optimize_query.py` | Converts a research idea into 3–5 optimized search queries |
| 📚 **Literature Search** | `search.py` | Multi-backend search (Crossref + OpenAlex), dedup by DOI |
| ✅ **Reference Verifier** | `verify_references.py` | Field-by-field RIS validation against Crossref metadata |

## Installation

```bash
git clone https://github.com/yourname/hydrology-literature-search.git
cd hydrology-literature-search
pip install requests  # only dependency
```

## Quick Start

```bash
# 1. Turn your idea into search queries
python scripts/optimize_query.py "SAR flood mapping with attention mechanism"

# 2. Search with the best query
python scripts/search.py --query "transformer flood sar" --max-results 20

# 3. Before submission: verify your reference list
python scripts/verify_references.py --ris manuscript_refs.ris
```

## Key Features

- **LLM-powered query optimization** — optional, falls back to free local mode
- **Chinese–English mixed input** — auto-detects and translates Chinese research terms
- **Dual-source verification** — Crossref + OpenAlex, NOT just DOI existence checks
- **Curated journal taxonomy** — 3-layer: hydrology, remote sensing, CS/ML venues with ISSNs
- **No API keys required** for search and verification (free Crossref/OpenAlex APIs)

## Why Reference Verification Matters

A prior verification that only checked `doi.org/XXX` → HTTP 200 found **zero** errors. Field-by-field comparison against Crossref metadata revealed **61% of references had errors**, including 10 wrong journal names. [Read the guide →](references/verification-guide.md)

## Documentation

- **[SKILL.md](SKILL.md)** — Complete workflow overview
- **[Search Guide](references/search-guide.md)** — Search strategies, filters, export formats
- **[Verification Guide](references/verification-guide.md)** — Full verification workflow with examples
- **[Journal Reference](references/journals.md)** — Three-layer curated journal list with ISSNs

## Journal Coverage

Three layers of academic venues:

1. **Hydrology & Water Resources** (15 journals) — Journal of Hydrology, WRR, HESS, etc.
2. **Remote Sensing & Earth Observation** (15 journals) — RSE, ISPRS, IEEE TGRS, etc.
3. **Computer Science & Machine Learning** (17 journals + 12 conferences) — NeurIPS, ICLR, ICML, CVPR, etc.

## Example Workflow

```
optimize_query.py  →  search.py  →  Zotero  →  write paper  →  export RIS  →  verify_references.py  →  clean RIS  →  submit
```

## Requirements

- Python 3.8+
- `requests` (`pip install requests`)
- Crossref + OpenAlex: free, no API keys needed
- LLM query optimization: needs OpenAI-compatible API key (optional)

## License

MIT — see [LICENSE](LICENSE).
