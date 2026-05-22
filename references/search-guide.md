# Literature Search Guide

Detailed workflows for the `search.py` tool in hydrology × remote sensing research.

## Basic Search

```bash
python scripts/search.py --query "SAR flood mapping deep learning" --max-results 20
```

### Output

Each result includes:
- Title, authors (abbreviated), year, DOI
- Abstract (truncated)
- Citation count + citations per year
- Journal/venue name
- Source backend (Crossref / OpenAlex)
- Open access status

### Dump full JSON for processing

```bash
python scripts/search.py --query "..." --max-results 20 > results.json
```

## Filtering

### By year range

```bash
python scripts/search.py --query "flood inundation model" \
    --year-start 2020 --year-end 2025
```

### By journal (comma-separated)

```bash
python scripts/search.py --query "U-Net flood segmentation" \
    --journal-filter "Journal of Hydrology,Remote Sensing of Environment,Water Resources Research"
```

### By minimum citation count

```bash
python scripts/search.py --query "spatial cross-validation" \
    --min-citations 10
```

### Combine filters

```bash
python scripts/search.py --query "deep learning streamflow prediction" \
    --year-start 2020 --min-citations 5 \
    --journal-filter "Journal of Hydrology,WRR,HESS"
```

## Export Formats

```bash
# BibTeX (import to Zotero/Mendeley)
python scripts/search.py --query "flood forecasting LSTM" --export bibtex -o refs.bib

# Markdown table
python scripts/search.py --query "SAR water extraction" --export markdown -o papers.md

# CSV
python scripts/search.py --query "hydrological model calibration" --export csv -o papers.csv

# Summary stats only (no paper list)
python scripts/search.py --query "climate change hydrology" --summary-only
```

## Search Strategies for Hydrology × RS × ML

### Strategy 1: Broad scan (new field)

1. Use the query optimizer: `python scripts/optimize_query.py "your idea" --llm`
2. Pick the best query and run with `--max-results 30 --year-start 2020`
3. Review titles, identify key journals and authors
4. Refine with `--journal-filter`

### Strategy 2: Method-focused search

```bash
# Find papers using a specific method
python scripts/search.py --query "U-Net flood inundation SAR Sentinel-1" --max-results 20
python scripts/search.py --query "Vision Transformer remote sensing flood" --max-results 20
python scripts/search.py --query "SHAP explainable flood susceptibility" --max-results 20
```

### Strategy 3: Application-focused search

```bash
python scripts/search.py --query "flood extent mapping SAR change detection" --max-results 20
python scripts/search.py --query "spatial cross-validation ecological model" --max-results 20
python scripts/search.py --query "compound flooding coastal pluvial" --max-results 20
```

### Strategy 4: Review hunting

```bash
python scripts/search.py --query "deep learning hydrology review" --max-results 15
python scripts/search.py --query "remote sensing flood mapping review survey" --max-results 15
python scripts/search.py --query "machine learning water resources review" --max-results 15
```

### Strategy 5: Citation chasing

1. Find a known key paper
2. Search for papers citing it (use Semantic Scholar or Google Scholar)
3. Search for papers with similar keywords + newer year range

## Single-Backend Mode

```bash
# OpenAlex only (better citation data)
python scripts/search.py --query "flood risk assessment" --backend openalex

# Crossref only (better metadata)
python scripts/search.py --query "water quality remote sensing" --backend crossref
```

## Tips

- **Too few results?** Broaden query, remove journal filter, increase `--max-results`
- **Too many results?** Add `--min-citations`, narrow year range, add `--journal-filter`
- **Want open-access papers?** Filter results JSON: `jq '.[] | select(.is_open_access)'`
- **Need full text?** Use `web_fetch` on DOI URLs for open-access papers
- **Building a reference list?** Export BibTeX → import to Zotero → manage there
