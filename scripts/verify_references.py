#!/usr/bin/env python3
"""
Reference verification & cleaning tool — Crossref + OpenAlex dual-source validation.

Reads a RIS file, extracts DOIs, fetches authoritative metadata from Crossref
and OpenAlex, does field-by-field comparison (NOT just HTTP 200 checks), and
generates:
  1. A clean RIS file with Crossref-corrected metadata
  2. A diff report (before/after for every changed entry)
  3. A verification report (per-entry: ✅ pass / ❌ fail / ⚠️ warning)
  4. A clickable DOI list (Markdown)

Usage:
    python verify_references.py --ris references.ris
    python verify_references.py --ris refs.ris --output-dir ./cleaned
    python verify_references.py --ris refs.ris --crossref-only
    python verify_references.py --ris refs.ris --no-clean  (report only, no RIS output)

Outputs (in --output-dir):
    *_CLEAN.ris           — RIS with Crossref-corrected metadata
    *_diff.txt            — before/after for every changed field
    *_verification.md     — per-entry Crossref + OpenAlex status
    *_doi_list.md         — clickable DOI links
"""

import argparse
import json
import re
import sys
import time
from difflib import unified_diff
from urllib.parse import quote_plus

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import requests
except ImportError:
    print("Error: pip install requests", file=sys.stderr)
    sys.exit(1)


# ─── RIS Parsing / Writing ───────────────────────────────────────────────────

def parse_ris(path):
    """Parse RIS file into list of dicts."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    # Split on end-of-record marker
    records_raw = content.strip().split("\nER  -")
    if not records_raw:
        return []
    entries = []
    for rec_raw in records_raw:
        if not rec_raw.strip():
            continue
        rec = {}
        for line in rec_raw.strip().split("\n"):
            m = re.match(r"^(\w{2})\s{2}-\s+(.*)", line)
            if not m:
                continue
            tag, val = m.group(1), m.group(2).strip()
            if tag == "AU":
                rec.setdefault("AU", [])
                if val not in rec["AU"]:
                    rec["AU"].append(val)
            elif tag != "N1":  # skip notes
                rec[tag] = val
        entries.append(rec)
    return entries


def write_ris(entries, path):
    """Write list of dicts to RIS file."""
    lines = []
    ty_map = {
        "JOUR": "JOUR", "CONF": "CONF", "BOOK": "BOOK",
        "CHAP": "CHAP", "RPRT": "RPRT", "THES": "THES",
    }
    for rec in entries:
        # Type
        ty = rec.get("TY", "JOUR")
        lines.append(f"TY  - {ty_map.get(ty, ty)}")
        for au in rec.get("AU", []):
            lines.append(f"AU  - {au}")
        for tag in ["TI", "T2", "JO", "JA", "PY", "VL", "IS", "SP", "EP", "DO", "UR", "PB", "CY"]:
            if tag in rec and rec[tag]:
                lines.append(f"{tag}  - {rec[tag]}")
        lines.append("ER  -")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─── Crossref API ────────────────────────────────────────────────────────────

def fetch_crossref(doi, timeout=15, max_retries=3):
    """Fetch full Crossref metadata for a DOI. Returns dict or None."""
    url = f"https://api.crossref.org/works/{quote_plus(doi)}"
    headers = {"User-Agent": "HydrologyRefVerifier/1.0 (mailto:research@example.com)"}
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 404:
                return {"_error": "DOI not found in Crossref"}
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code != 200:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return {"_error": f"HTTP {r.status_code}"}
            data = r.json()
            msg = data.get("message", {})
            return _normalize_crossref(msg)
        except (requests.ConnectionError, requests.Timeout,
                ConnectionResetError, ConnectionAbortedError) as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return {"_error": str(e)[:60]}
        except Exception as e:
            return {"_error": str(e)[:60]}


def _normalize_crossref(msg):
    """Extract standard fields from Crossref message."""
    rec = {}
    # Authors
    authors = []
    for a in msg.get("author", []):
        family = a.get("family", "")
        given = a.get("given", "")
        authors.append(f"{family}, {given}")
    rec["AU"] = authors

    # Title
    title_list = msg.get("title", [])
    rec["TI"] = title_list[0] if title_list else ""

    # Container (journal / conference)
    container = msg.get("container-title", [])
    rec["JO"] = container[0] if container else ""

    # Type
    rec["TY"] = msg.get("type", "journal-article")

    # Year
    issued = msg.get("issued", {})
    date_parts = issued.get("date-parts", [[None]])
    rec["PY"] = str(date_parts[0][0]) if date_parts[0][0] else ""

    # Volume, issue, pages
    rec["VL"] = msg.get("volume", "")
    rec["IS"] = msg.get("issue", "")
    rec["SP"] = msg.get("page", "")
    # Handle various page formats: "123-145", "pp. 123–145", "S31-S49"
    if rec["SP"]:
        sp = rec["SP"].strip().replace("pp. ", "").replace("pp.", "")
        # Try en-dash first, then hyphen
        for sep in ["–", "—", "-"]:
            if sep in sp:
                parts = sp.split(sep, 1)
                rec["SP"] = parts[0].strip()
                rec["EP"] = parts[1].strip() if len(parts) > 1 else ""
                break
        else:
            rec["SP"] = sp
            rec["EP"] = ""
    else:
        rec["EP"] = ""

    rec["DO"] = msg.get("DOI", "")
    rec["UR"] = f"https://doi.org/{rec['DO']}" if rec["DO"] else ""

    return rec


# ─── OpenAlex API ────────────────────────────────────────────────────────────

def fetch_openalex(doi, timeout=15):
    """Fetch OpenAlex metadata for a DOI. Returns dict or None."""
    url = f"https://api.openalex.org/works/doi:{doi}"
    headers = {"User-Agent": "mailto:research@example.com"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 404:
            return {"_error": "DOI not found in OpenAlex"}
        if r.status_code != 200:
            return {"_error": f"HTTP {r.status_code}"}
        data = r.json()
        return _normalize_openalex(data)
    except requests.Timeout:
        return {"_error": "Request timeout"}
    except Exception as e:
        return {"_error": str(e)}


def _normalize_openalex(data):
    """Extract standard fields from OpenAlex record."""
    rec = {}
    # Authors
    authors = []
    for a in data.get("authorships", []):
        au = a.get("author", {})
        family = au.get("display_name", "").split()[-1] if au.get("display_name") else ""
        given = " ".join(au.get("display_name", "").split()[:-1]) if au.get("display_name") else ""
        authors.append(f"{family}, {given}")
    rec["AU"] = authors

    rec["TI"] = data.get("display_name", data.get("title", ""))
    src = data.get("primary_location", {}).get("source", {})
    rec["JO"] = src.get("display_name", "") if src else data.get("host_venue", {}).get("name", "")

    rec["TY"] = data.get("type", "journal-article")
    rec["PY"] = str(data.get("publication_year", ""))
    biblio = data.get("biblio", {})
    rec["VL"] = biblio.get("volume", "")
    rec["IS"] = biblio.get("issue", "")
    rec["SP"] = biblio.get("first_page", "")
    ep = biblio.get("last_page", "")
    rec["EP"] = ep if ep and ep != rec["SP"] else ""

    rec["DO"] = data.get("doi", "")

    return rec


# ─── Field Comparison ────────────────────────────────────────────────────────

CROSSREF_FIELD_MAP = {
    "JO": "journal name",
    "VL": "volume",
    "IS": "issue",
    "SP": "first page",
    "EP": "last page",
    "PY": "year",
}

# Crossref type → RIS type mapping
TY_CROSSREF_TO_RIS = {
    "journal-article": "JOUR",
    "proceedings-article": "CONF",
    "book": "BOOK",
    "book-chapter": "CHAP",
    "report": "RPRT",
    "dissertation": "THES",
    "monograph": "BOOK",
    "reference-entry": "JOUR",
    "journal-issue": "JOUR",
}

def compare_fields(ris_rec, crossref_rec):
    """
    Compare RIS fields against Crossref fields.
    Returns (is_clean, list of diffs).
    Year ±1 is treated as a warning (online-first vs print).
    TY is normalized (journal-article ↔ JOUR, etc.).
    """
    diffs = []
    for field, label in CROSSREF_FIELD_MAP.items():
        ris_val = (ris_rec.get(field, "") or "").strip().rstrip(".")
        cr_val = (crossref_rec.get(field, "") or "").strip().rstrip(".")
        if not cr_val:
            continue
        if ris_val.lower() != cr_val.lower():
            tolerance = False
            if field == "PY":
                try:
                    if abs(int(ris_val) - int(cr_val)) <= 1:
                        tolerance = True
                except ValueError:
                    pass
            if tolerance:
                diffs.append({
                    "field": field, "label": label,
                    "ris": ris_val, "crossref": cr_val,
                    "warning": True
                })
            else:
                diffs.append({
                    "field": field, "label": label,
                    "ris": ris_val, "crossref": cr_val,
                    "warning": False
                })

    # TY comparison (normalized)
    ris_ty = (ris_rec.get("TY", "") or "").strip()
    cr_ty_raw = (crossref_rec.get("TY", "") or "").strip()
    cr_ty_normalized = TY_CROSSREF_TO_RIS.get(cr_ty_raw, cr_ty_raw)
    if cr_ty_raw and ris_ty and ris_ty != cr_ty_normalized:
        diffs.append({
            "field": "TY", "label": "document type",
            "ris": ris_ty, "crossref": f"{cr_ty_raw} → {cr_ty_normalized}",
            "warning": False
        })

    return len([d for d in diffs if not d["warning"]]) == 0, diffs


# ─── Correct RIS Entry ───────────────────────────────────────────────────────

def correct_entry(ris_rec, crossref_rec):
    """Return corrected RIS entry using Crossref as ground truth."""
    corrected = dict(ris_rec)  # keep everything, especially AU list
    if "_error" in crossref_rec:
        return corrected  # can't correct

    for field in ["JO", "JA", "VL", "IS", "SP", "EP"]:
        val = crossref_rec.get(field, "")
        if val:
            corrected[field] = str(val).strip()

    # Year
    if crossref_rec.get("PY"):
        corrected["PY"] = str(crossref_rec["PY"])

    # Type
    cr_type = crossref_rec.get("TY", "")
    ty_map = {
        "journal-article": "JOUR",
        "proceedings-article": "CONF",
        "book": "BOOK",
        "book-chapter": "CHAP",
        "report": "RPRT",
        "dissertation": "THES",
    }
    if cr_type in ty_map:
        corrected["TY"] = ty_map[cr_type]

    # Title
    if crossref_rec.get("TI"):
        corrected["TI"] = crossref_rec["TI"]

    return corrected


# ─── Report Generation ───────────────────────────────────────────────────────

def format_authors(entry):
    """Format RIS author list for display."""
    aus = entry.get("AU", [])
    if not aus:
        return "(unknown)"
    n = len(aus)
    if n == 1:
        return aus[0].split(",")[0].strip()
    elif n == 2:
        return f"{aus[0].split(',')[0].strip()} & {aus[1].split(',')[0].strip()}"
    else:
        return f"{aus[0].split(',')[0].strip()} et al."


def short_title(entry):
    """Shorten title for display."""
    t = entry.get("TI", "")
    return t[:80] + "..." if len(t) > 80 else t


def generate_diff_report(entries, crossref_data, path):
    """Generate before/after diff for all changed entries."""
    lines = []
    lines.append("=" * 70)
    lines.append("RIS Reference Diff Report — Crossref vs Original")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)
    lines.append("")

    changed_count = 0
    for i, entry in enumerate(entries, 1):
        cr = crossref_data[i]
        if "_error" in cr:
            continue
        _, diffs = compare_fields(entry, cr)
        if not diffs:
            continue
        changed_count += 1
        lines.append(f"[{i}] {format_authors(entry)} ({entry.get('PY', '?')})")
        lines.append(f"    Title: {short_title(entry)}")
        lines.append("")
        for d in diffs:
            marker = "⚠️ (year ±1)" if d["warning"] else "❌"
            lines.append(f"    {marker} {d['label']}:")
            lines.append(f"          RIS:      {d['ris']}")
            lines.append(f"          Crossref: {d['crossref']}")
        lines.append("")

    lines.append("-" * 70)
    lines.append(f"Summary: {changed_count} entries changed out of {len(entries)} total")
    lines.append("=" * 70)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_verification_report(entries, crossref_data, openalex_data, path):
    """Generate Markdown verification report with Crossref + OpenAlex status."""
    lines = []
    lines.append("# Reference Verification Report")
    lines.append(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Sources:** Crossref API + OpenAlex API")
    lines.append("")
    lines.append("| # | Authors | Year | Crossref | OpenAlex | Notes |")
    lines.append("|---|---------|------|----------|----------|-------|")

    cr_ok, cr_err, oa_ok, oa_err = 0, 0, 0, 0

    for i, entry in enumerate(entries, 1):
        cr = crossref_data.get(i, {})
        oa = openalex_data.get(i, {})

        authors = format_authors(entry)
        year = entry.get("PY", "?")

        # Crossref status
        if "_error" in cr:
            cr_status = f"❌ {cr['_error'][:30]}"
            cr_err += 1
            cr_ok_val = False
        else:
            is_clean, diffs = compare_fields(entry, cr)
            if is_clean:
                cr_status = "✅"
                cr_ok += 1
            else:
                err_count = len([d for d in diffs if not d["warning"]])
                warn_count = len([d for d in diffs if d["warning"]])
                parts = []
                if err_count:
                    parts.append(f"❌ {err_count} fields")
                if warn_count:
                    parts.append(f"⚠️ {warn_count}")
                cr_status = ", ".join(parts) if parts else "✅"
                if err_count:
                    cr_err += 1
                else:
                    cr_ok += 1
                cr_ok_val = err_count == 0

        # OpenAlex status (just existence + year check, lighter)
        if "_error" in oa:
            oa_status = f"❌ {oa['_error'][:30]}"
            oa_err += 1
        else:
            oa_year = oa.get("PY", "")
            entry_year = entry.get("PY", "")
            if oa_year and entry_year and abs(int(oa_year) - int(entry_year)) <= 1:
                oa_status = "✅"
                oa_ok += 1
            elif oa_year == entry_year:
                oa_status = "✅"
                oa_ok += 1
            else:
                oa_status = f"⚠️ yr:{oa_year}"
                oa_ok += 1

        # Notes
        notes = ""
        if "_error" not in cr:
            _, diffs = compare_fields(entry, cr)
            diff_fields = [d["label"] for d in diffs if not d["warning"]]
            if diff_fields:
                notes = "Mismatch: " + ", ".join(diff_fields[:3])

        lines.append(f"| [{i}] | {authors} | {year} | {cr_status} | {oa_status} | {notes} |")

    lines.append("")
    lines.append(f"**Crossref:** {cr_ok} ✅ / {cr_err} ❌  |  **OpenAlex:** {oa_ok} ✅ / {oa_err} ❌")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_doi_list(entries, path):
    """Generate clickable DOI list in Markdown."""
    lines = []
    lines.append("# Clickable DOI List")
    lines.append("")
    for i, entry in enumerate(entries, 1):
        doi = entry.get("DO", "")
        title = short_title(entry)
        if doi:
            lines.append(f"**[{i}]** [{title}](https://doi.org/{doi})")
        else:
            lines.append(f"**[{i}]** {title} *(no DOI)*")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Verify and clean RIS references against Crossref + OpenAlex metadata."
    )
    parser.add_argument("--ris", required=True, help="Input RIS file path")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input)")
    parser.add_argument("--crossref-only", action="store_true", help="Skip OpenAlex, use Crossref only")
    parser.add_argument("--no-clean", action="store_true", help="Report only, don't generate clean RIS")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    # Parse
    print(f"📖 Parsing: {args.ris}", flush=True)
    entries = parse_ris(args.ris)
    if not entries:
        print("No entries found in RIS file.", flush=True)
        sys.exit(1)
    print(f"   Found {len(entries)} entries", flush=True)

    # Output directory
    import os
    if args.output_dir:
        out_dir = args.output_dir
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = os.path.dirname(args.ris) or "."
    base = os.path.splitext(os.path.basename(args.ris))[0]

    # Fetch Crossref metadata
    print(f"\n🔍 Fetching Crossref metadata...", flush=True)
    crossref_data = {}
    for i, entry in enumerate(entries, 1):
        doi = entry.get("DO", "")
        if not doi:
            print(f"   [{i}] ❌ No DOI — skipping", flush=True)
            crossref_data[i] = {"_error": "No DOI"}
            continue
        cr = fetch_crossref(doi)
        crossref_data[i] = cr
        if "_error" in cr:
            print(f"   [{i}] ❌ {cr['_error']} — {doi}", flush=True)
        else:
            _, diffs = compare_fields(entry, cr)
            errs = [d for d in diffs if not d["warning"]]
            warns = [d for d in diffs if d["warning"]]
            if errs:
                print(f"   [{i}] ❌ {len(errs)} field mismatch(es): {doi}", flush=True)
            elif warns:
                print(f"   [{i}] ⚠️  {len(warns)} warning(s): {doi}", flush=True)
            else:
                print(f"   [{i}] ✅ {doi}", flush=True)
        time.sleep(args.delay)

    # Fetch OpenAlex (optional)
    openalex_data = {}
    if not args.crossref_only:
        print(f"\n🔍 Fetching OpenAlex metadata...", flush=True)
        for i, entry in enumerate(entries, 1):
            doi = entry.get("DO", "")
            if not doi:
                openalex_data[i] = {"_error": "No DOI"}
                continue
            oa = fetch_openalex(doi)
            openalex_data[i] = oa
            if "_error" in oa:
                print(f"   [{i}] ❌ {oa['_error']}", flush=True)
            else:
                print(f"   [{i}] ✅", flush=True)
            time.sleep(args.delay)

    # Generate clean RIS
    if not args.no_clean:
        clean_path = os.path.join(out_dir, f"{base}_CLEAN.ris")
        print(f"\n📝 Writing clean RIS → {clean_path}", flush=True)
        corrected_entries = []
        for i, entry in enumerate(entries, 1):
            cr = crossref_data.get(i, {})
            corrected = correct_entry(entry, cr)
            corrected_entries.append(corrected)
        write_ris(corrected_entries, clean_path)

        # Also verify the clean RIS with a second pass
        print(f"   Re-verifying clean RIS...", flush=True)
        recheck_entries = parse_ris(clean_path)
        cr_ok = 0
        for i, entry in enumerate(recheck_entries, 1):
            doi = entry.get("DO", "")
            if not doi:
                continue
            cr = fetch_crossref(doi)
            if "_error" not in cr:
                is_clean, _ = compare_fields(entry, cr)
                if is_clean:
                    cr_ok += 1
            time.sleep(args.delay)
        print(f"   Clean RIS: {cr_ok}/{len([e for e in recheck_entries if e.get('DO')])} pass Crossref validation", flush=True)

    # Generate reports
    print(f"\n📊 Generating reports...", flush=True)

    diff_path = os.path.join(out_dir, f"{base}_diff.txt")
    generate_diff_report(entries, crossref_data, diff_path)
    print(f"   Diff report → {diff_path}", flush=True)

    verify_path = os.path.join(out_dir, f"{base}_verification.md")
    generate_verification_report(entries, crossref_data, openalex_data, verify_path)
    print(f"   Verification report → {verify_path}", flush=True)

    doi_list_path = os.path.join(out_dir, f"{base}_doi_list.md")
    generate_doi_list(entries, doi_list_path)
    print(f"   DOI list → {doi_list_path}", flush=True)

    # Summary
    total = len(entries)
    has_doi = sum(1 for e in entries if e.get("DO"))
    cr_errors = sum(1 for cr in crossref_data.values() if "_error" in cr)
    field_errors = 0
    for i, entry in enumerate(entries, 1):
        cr = crossref_data.get(i, {})
        if "_error" not in cr:
            _, diffs = compare_fields(entry, cr)
            field_errors += len([d for d in diffs if not d["warning"]])

    print(f"\n{'='*60}", flush=True)
    print(f"SUMMARY: {field_errors} field errors across {cr_errors + field_errors} entries", flush=True)
    print(f"  Total entries: {total}, with DOI: {has_doi}", flush=True)
    print(f"  Crossref unavailable: {cr_errors}", flush=True)
    print(f"  Field mismatches corrected: {field_errors}", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
