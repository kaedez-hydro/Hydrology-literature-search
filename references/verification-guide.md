# Reference Verification Guide

Detailed workflows for `verify_references.py`. Validates RIS reference lists
against Crossref metadata — field by field, not just DOI existence.

**Critical principle:** A DOI resolving to a 200 OK page proves the paper EXISTS.
It does NOT prove your journal name, volume, issue, or page numbers are correct.
Only field-by-field comparison catches these errors.

## Quick Start

```bash
python scripts/verify_references.py --ris manuscript_references.ris
```

## What Gets Checked

| RIS Field | Source | Tolerance |
|-----------|--------|-----------|
| Journal name (JO) | Crossref `container-title` | Exact (case-insensitive) |
| Volume (VL) | Crossref `volume` | Exact |
| Issue (IS) | Crossref `issue` | Exact |
| Start page (SP) | Crossref `page` (parsed) | Exact |
| End page (EP) | Crossref `page` (parsed) | Exact |
| Year (PY) | Crossref `issued` | ±1 year (online-first vs print) |
| Document type (TY) | Crossref `type` | Normalized (`journal-article` ↔ `JOUR`) |

## Output Files

| File | Purpose |
|------|---------|
| `*_CLEAN.ris` | Corrected RIS — import into Zotero/Endnote |
| `*_diff.txt` | Every changed field: before → after |
| `*_verification.md` | Per-entry status table (Crossref + OpenAlex) |
| `*_doi_list.md` | All DOIs as clickable links for manual spot-check |

## Usage Options

```bash
# Full dual-source verification (Crossref + OpenAlex)
python scripts/verify_references.py --ris refs.ris

# Crossref only (faster, ~0.5s per DOI)
python scripts/verify_references.py --ris refs.ris --crossref-only

# Report only, don't generate clean RIS
python scripts/verify_references.py --ris refs.ris --no-clean

# Custom output directory
python scripts/verify_references.py --ris refs.ris --output-dir ./verified

# Adjust API delay (default: 0.5s)
python scripts/verify_references.py --ris refs.ris --delay 0.3
```

## Verification Workflow

### Step 1: Run initial check

```bash
python scripts/verify_references.py --ris my_paper_refs.ris
```

This produces 4 files. Start with the verification report.

### Step 2: Review the verification report

Open `*_verification.md`. Each entry gets:

| Status | Meaning |
|--------|---------|
| ✅ | All fields match Crossref |
| ❌ N fields | N fields disagree with Crossref |
| ⚠️ | Year differs by ±1 (likely online-first issue) |
| ❌ DOI not found | DOI not indexed in Crossref (DataCite/arXiv) |

### Step 3: Review the diff report

Open `*_diff.txt`. Shows every field change entry by entry:

```
[3] Pappenberger (2008)
    Title: Multi-method global sensitivity analysis...

    ❌ journal name:
          RIS:      Water Resources Research
          Crossref: Advances in Water Resources

    ❌ volume:
          RIS:      44
          Crossref: 31
```

### Step 4: Spot-check critical changes

Pay special attention to:
- **Journal name changes** — these are the most visible errors to reviewers
- **Year changes** — could affect your inline citations
- **Missing page numbers** — Crossref may have them even if your RIS doesn't

### Step 5: Handle special cases

**arXiv preprints** (DOI starts with `10.48550/`):
- Crossref cannot verify these (registered with DataCite)
- Manually check against the paper's official publication venue
- Example: Lundberg & Lee (2017) NeurIPS — DOI at DataCite, metadata verified from NeurIPS proceedings

**Connection errors**:
- The script retries up to 3 times with exponential backoff
- If persistent, try `--delay 1.0` for slower, more reliable fetching

### Step 6: Use the clean RIS

```bash
# The clean RIS is already generated
my_paper_refs_CLEAN.ris   # ← use this in your reference manager

# Re-verify to confirm (should show 0 field errors)
python scripts/verify_references.py --ris my_paper_refs_CLEAN.ris --crossref-only
```

### Step 7: Regenerate formatted citations

After importing the clean RIS into Zotero/Endnote, re-export your formatted reference list. Many journal/volume/page fields changed, so formatted citations will differ.

### Step 8: Cross-check body text

Inline citations (e.g., "Arnell, 1999" or "(Pappenberger et al., 2008)") usually don't change since authors and years are mostly preserved. But verify any entries where the year changed by more than ±1.

## Common Error Patterns Found in Real Papers

From a 51-reference manuscript verification:

| Error Type | Count | Example |
|------------|-------|---------|
| Wrong journal name | 10 | "WRR" actually "Advances in Water Resources" |
| Wrong volume | 8 | "529" vs actual "590" |
| Wrong issue | 4 | Missing issue numbers |
| Wrong pages | 12 | Incomplete or incorrect page ranges |
| Wrong year | 3 | Online-first year vs print year |
| Wrong document type | 4 | "JOUR" for conference proceedings |
| No errors | 20 | Only 39% were correct |

## ⚠️ Critical Warning

**A prior verification pass that only checked `doi.org/XXX` → HTTP 200 found zero errors.**
The same references, when checked field-by-field against Crossref, had **61% error rate**.
Ten wrong journal names would have been immediately caught by reviewers.

Always run field-by-field verification before manuscript submission.
