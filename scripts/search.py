#!/usr/bin/env python3
"""
Multi-backend hydrology literature search.

Backends:
- crossref   : Crossref REST API (free, no key needed) — best for DOI/metadata
- openalex   : OpenAlex REST API (free, no key needed) — best for citation data
- semantic   : Semantic Scholar API (needs free API key) — best for ML/AI papers

Usage:
    python search.py --query "rainfall runoff model" --max-results 20 --year-start 2020
    python search.py --query "groundwater recharge" --backend openalex --export bibtex
    python search.py --query "flood forecasting" --journal-filter "Journal of Hydrology,Water Resources Research"

Output: JSON with unified format, deduplicated by DOI.
"""

import argparse
import json
import re
import sys
import time
import hashlib
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import quote_plus

# Fix Windows stdout encoding for Unicode characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


# ─── Constants ───────────────────────────────────────────────────────────────

HYDROLOGY_JOURNALS = {
    # Top tier
    "Journal of Hydrology": "0022-1694",
    "Water Resources Research": "0043-1397",
    "Hydrology and Earth System Sciences": "1607-7938",
    "Hydrological Processes": "1099-1085",
    # Water resources
    "Water Resources Management": "1573-1650",
    "Journal of Hydrology: Regional Studies": "2214-5818",
    # Water quality
    "Water Research": "0043-1354",
    "Science of The Total Environment": "0048-9697",
    # Remote sensing
    "Remote Sensing of Environment": "0034-4257",
    "Journal of Hydrometeorology": "1525-7541",
    # Climate
    "Journal of Climate": "0894-8755",
    # Groundwater
    "Hydrogeology Journal": "1435-0157",
    "Groundwater": "1745-6584",
}

HYDROLOGY_KEYWORDS = [
    "hydrology", "water resources", "hydrological", "watershed", "catchment",
    "groundwater", "surface water", "rainfall", "runoff", "streamflow",
    "flood", "drought", "evapotranspiration", "infiltration", "precipitation",
    "water quality", "aquifer", "hydrogeology", "hydrometeorology",
    "eco-hydrology", "snow", "glacier", "reservoir", "irrigation"
]

USER_AGENT = "HydrologyLiteratureSearch/2.0 (mailto:researcher@example.com)"


# ─── Unified Paper Record ────────────────────────────────────────────────────

def make_paper(title, authors, year, doi, abstract, citations, venue, source,
               url="", citations_per_year=None, is_open_access=False):
    return {
        "title": title or "Unknown",
        "authors": authors or [],
        "year": year,
        "doi": doi or "",
        "abstract": abstract or "",
        "citations": citations or 0,
        "citations_per_year": citations_per_year or {},
        "venue": venue or "",
        "source": source,
        "url": url or f"https://doi.org/{doi}" if doi else "",
        "is_open_access": is_open_access,
    }


# ─── Crossref Backend ────────────────────────────────────────────────────────

def search_crossref(query, max_results=20, year_start=None, year_end=None,
                    journal_filter=None, min_citations=None):
    """Search Crossref REST API."""
    base_url = "https://api.crossref.org/works"
    results = []
    rows = min(max_results, 100)
    offset = 0

    while len(results) < max_results:
        # Build filter
        filters = []
        if year_start:
            filters.append(f"from-pub-date:{year_start}-01-01")
        if year_end:
            filters.append(f"until-pub-date:{year_end}-12-31")

        params = {
            "query": query,
            "rows": rows,
            "offset": offset,
        }
        if filters:
            params["filter"] = ",".join(filters)

        try:
            # Use params list as tuples to avoid encoding issues
            req_url = f"{base_url}?query={quote_plus(query)}&rows={rows}&offset={offset}"
            if filters:
                req_url += f"&filter={quote_plus(','.join(filters))}"
            r = requests.get(req_url, timeout=15,
                           headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                print(f"[Crossref] HTTP {r.status_code}", file=sys.stderr)
                break
            data = r.json()
        except Exception as e:
            print(f"[Crossref] Error: {e}", file=sys.stderr)
            break

        items = data.get("message", {}).get("items", [])
        if not items:
            break

        for item in items:
            # Extract title
            title_list = item.get("title", [])
            title = title_list[0] if title_list else None
            if not title:
                continue

            # Authors
            authors = []
            for a in item.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                authors.append(f"{family}, {given}".strip(", "))

            # Year from created date
            created = item.get("created", {}).get("date-parts", [[None]])[0]
            year = created[0] if created else None

            # DOI
            doi = item.get("DOI", "")

            # Venue
            container = item.get("container-title", [])
            venue = container[0] if container else ""

            # Journal filter
            if journal_filter and journal_filter.lower() not in venue.lower():
                continue

            # Citations (referenced-by count)
            citations = item.get("is-referenced-by-count", 0)

            # Abstract
            abstract = item.get("abstract", "")
            # Strip HTML tags from abstract
            abstract = re.sub(r"<[^>]+>", "", abstract) if abstract else ""

            if min_citations and citations < min_citations:
                continue

            results.append(make_paper(
                title=title, authors=authors, year=year, doi=doi,
                abstract=abstract, citations=citations, venue=venue,
                source="Crossref"
            ))

        total = data.get("message", {}).get("total-results", 0)
        offset += rows
        if offset >= min(total, 1000):
            break
        time.sleep(0.3)  # Be polite

    return results[:max_results]


# ─── OpenAlex Backend ────────────────────────────────────────────────────────

def search_openalex(query, max_results=20, year_start=None, year_end=None,
                    journal_filter=None, min_citations=None):
    """Search OpenAlex REST API."""
    base_url = "https://api.openalex.org/works"
    results = []
    page = 1
    per_page = min(max_results, 200)

    params = {
        "search": query,
        "per_page": per_page,
        "page": page,
    }
    if journal_filter:
        params["filter"] = f"primary_location.source.display_name.search:{journal_filter}"

    while len(results) < max_results:
        params["page"] = page
        try:
            r = requests.get(base_url, params=params, timeout=15,
                           headers={"User-Agent": USER_AGENT, "mailto": "researcher@example.com"})
            if r.status_code != 200:
                print(f"[OpenAlex] HTTP {r.status_code}", file=sys.stderr)
                break
            data = r.json()
        except Exception as e:
            print(f"[OpenAlex] Error: {e}", file=sys.stderr)
            break

        items = data.get("results", [])
        if not items:
            break

        for item in items:
            title = item.get("title", "")
            if not title:
                continue

            # Year
            year = item.get("publication_year")

            # Year range filter
            if year_start and year and year < year_start:
                continue
            if year_end and year and year > year_end:
                continue

            # Authors
            authors = []
            for a in item.get("authorships", []):
                name = a.get("author", {}).get("display_name", "")
                if name:
                    authors.append(name)

            # DOI
            doi = item.get("doi", "").replace("https://doi.org/", "")

            # Venue
            src = item.get("primary_location", {}).get("source", {}) or {}
            venue = src.get("display_name", "")

            # Journal filter (if not already in params)
            if journal_filter and journal_filter.lower() not in venue.lower():
                continue

            # Citations
            citations = item.get("cited_by_count", 0)
            citations_per_year = {}
            for entry in item.get("counts_by_year", []):
                y = entry.get("year")
                c = entry.get("cited_by_count")
                if y and c:
                    citations_per_year[str(y)] = c

            if min_citations and citations < min_citations:
                continue

            # Abstract
            abstract = ""
            if item.get("abstract_inverted_index"):
                try:
                    idx = item["abstract_inverted_index"]
                    words = [""] * (max(idx.values(), key=lambda v: max(v) if v else 0)[-1] + 1 if idx else 0)
                    for word, positions in idx.items():
                        for pos in positions:
                            if pos < len(words):
                                words[pos] = word
                    abstract = " ".join(words)
                except Exception:
                    pass

            # Open access
            is_oa = item.get("open_access", {}).get("is_oa", False)

            results.append(make_paper(
                title=title, authors=authors, year=year, doi=doi,
                abstract=abstract, citations=citations, venue=venue,
                source="OpenAlex",
                citations_per_year=citations_per_year,
                is_open_access=is_oa
            ))

        page += 1
        if page > 10:  # Safety limit
            break
        time.sleep(0.3)

    return results[:max_results]


# ─── Deduplication ───────────────────────────────────────────────────────────

def title_similarity(t1, t2):
    """Get similarity ratio between two titles."""
    t1 = re.sub(r"[^a-zA-Z0-9\s]", "", t1.lower()).strip()
    t2 = re.sub(r"[^a-zA-Z0-9\s]", "", t2.lower()).strip()
    return SequenceMatcher(None, t1, t2).ratio()


def deduplicate(papers, threshold=0.85):
    """Merge duplicate papers by DOI or title similarity, keeping most complete record."""
    merged = []
    seen_dois = set()
    seen_titles = []

    for paper in papers:
        doi = paper.get("doi", "").lower().strip()

        # Exact DOI match
        if doi and doi in seen_dois:
            # Merge into existing
            for i, existing in enumerate(merged):
                if existing.get("doi", "").lower().strip() == doi:
                    # Keep the one with more citations or more complete record
                    if (paper.get("citations", 0) > existing.get("citations", 0) or
                            (paper.get("abstract") and not existing.get("abstract"))):
                        merged[i] = paper
                    break
            continue

        # Title similarity check
        is_dup = False
        for i, (existing, _) in enumerate(seen_titles):
            if title_similarity(paper["title"], existing["title"]) >= threshold:
                is_dup = True
                if (paper.get("citations", 0) > existing.get("citations", 0) or
                        (paper.get("abstract") and not existing.get("abstract"))):
                    merged[i] = paper
                    seen_titles[i] = (paper, paper["title"])
                break

        if not is_dup:
            merged.append(paper)
            if doi:
                seen_dois.add(doi)
            seen_titles.append((paper, paper["title"]))

    return merged


# ─── Export Helpers ──────────────────────────────────────────────────────────

def to_bibtex_entry(paper, index):
    """Convert a paper to BibTeX entry."""
    title = paper["title"].replace("{", "\\{").replace("}", "\\}")
    doi = paper["doi"]
    year = paper["year"] or ""

    # Author list: "Family, Given and Family, Given"
    authors = paper["authors"][:6]  # max 6 for entry key
    author_str = " and ".join(authors) if authors else "Unknown"

    # Generate entry key
    key = ""
    if authors:
        key = authors[0].split(",")[0].strip().replace(" ", "")
        key = re.sub(r"[^a-zA-Z]", "", key)
    if year:
        key += str(year)
    # Add first significant title word
    title_words = [w for w in title.split() if len(w) > 3 and w.lower() not in ("the", "and", "for", "with", "from")]
    if title_words:
        key += title_words[0].title()
    key = re.sub(r"[^a-zA-Z0-9]", "", key)[:30]

    lines = [f"@article{{{key},"]
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  author = {{{' and '.join(authors)}}},")
    if paper["venue"]:
        lines.append(f"  journal = {{{paper['venue']}}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if paper["url"]:
        lines.append(f"  url = {{{paper['url']}}},")
    if paper["abstract"]:
        abstract = paper["abstract"][:500].replace("{", "\\{").replace("}", "\\}")
        lines.append(f"  abstract = {{{abstract}}},")
    lines.append("}")
    return "\n".join(lines)


def to_markdown_table(papers):
    """Convert results to markdown table."""
    rows = ["| # | Title | Year | Citations | Journal | DOI |",
            "|---|-------|------|-----------|---------|-----|"]
    for i, p in enumerate(papers, 1):
        title = p["title"][:60] + ("..." if len(p["title"]) > 60 else "")
        year = str(p["year"]) if p["year"] else "-"
        citations = str(p["citations"])
        venue = p["venue"][:30] + ("..." if len(p["venue"]) > 30 else "") if p["venue"] else "-"
        doi = f"[{p['doi'][:15]}...](https://doi.org/{p['doi']})" if p["doi"] else "-"
        rows.append(f"| {i} | {title} | {year} | {citations} | {venue} | {doi} |")
    return "\n".join(rows)


def to_csv(papers):
    """Convert results to CSV."""
    import io
    import csv as csv_mod
    output = io.StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(["title", "authors", "year", "citations", "venue", "doi", "source", "open_access"])
    for p in papers:
        writer.writerow([
            p["title"],
            "; ".join(p["authors"]),
            p["year"] or "",
            p["citations"],
            p["venue"],
            p["doi"],
            p["source"],
            "yes" if p.get("is_open_access") else "no",
        ])
    return output.getvalue()


def build_summary(papers, query):
    """Build a summary of search results."""
    years = [p["year"] for p in papers if p["year"]]
    citations = [p["citations"] for p in papers]
    sources = {}
    venues = {}
    oa_count = sum(1 for p in papers if p.get("is_open_access"))

    for p in papers:
        src = p["source"]
        sources[src] = sources.get(src, 0) + 1
        v = p["venue"]
        if v:
            venues[v] = venues.get(v, 0) + 1

    top_venues = sorted(venues.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "query": query,
        "total": len(papers),
        "year_range": f"{min(years)}-{max(years)}" if years else "N/A",
        "avg_citations": round(sum(citations) / len(citations), 1) if citations else 0,
        "open_access_count": oa_count,
        "sources": sources,
        "top_venues": [{"venue": v, "count": c} for v, c in top_venues],
        "timestamp": datetime.now().isoformat(),
    }


# ─── Main CLI ────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Multi-backend hydrology literature search"
    )
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--max-results", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--year-start", type=int, help="Earliest publication year")
    parser.add_argument("--year-end", type=int, help="Latest publication year")
    parser.add_argument("--backend", choices=["all", "crossref", "openalex", "semantic"],
                        default="all", help="Search backend(s) (default: all)")
    parser.add_argument("--journal-filter", help="Filter by journal name (comma-separated)")
    parser.add_argument("--min-citations", type=int, help="Minimum citation count")
    parser.add_argument("--export", choices=["json", "bibtex", "markdown", "csv"],
                        default="json", help="Export format (default: json)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip deduplication")
    parser.add_argument("--summary-only", action="store_true", help="Only show summary, not full results")
    parser.add_argument("-o", "--output", help="Output file path")
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"""
╔══════════════════════════════════════════════╗
║   Hydrology Literature Search v2.0           ║
╚══════════════════════════════════════════════╝
""", file=sys.stderr)
    print(f"[*] Query:    {args.query}", file=sys.stderr)
    print(f"[*] Backend:  {args.backend}", file=sys.stderr)
    print(f"[*] Max:      {args.max_results}", file=sys.stderr)
    if args.year_start:
        print(f"[*] Years:    {args.year_start}-{args.year_end or 'present'}", file=sys.stderr)
    if args.journal_filter:
        print(f"[*] Journal:  {args.journal_filter}", file=sys.stderr)
    print(file=sys.stderr)

    all_papers = []
    per_backend = args.max_results if args.backend == "all" else args.max_results

    # Run selected backends
    if args.backend in ("all", "crossref"):
        print("[Crossref] Searching...", file=sys.stderr)
        papers = search_crossref(
            args.query, per_backend,
            args.year_start, args.year_end,
            args.journal_filter, args.min_citations
        )
        print(f"[Crossref] Found {len(papers)} results", file=sys.stderr)
        all_papers.extend(papers)

    if args.backend in ("all", "openalex"):
        print("[OpenAlex] Searching...", file=sys.stderr)
        papers = search_openalex(
            args.query, per_backend,
            args.year_start, args.year_end,
            args.journal_filter, args.min_citations
        )
        print(f"[OpenAlex] Found {len(papers)} results", file=sys.stderr)
        all_papers.extend(papers)

    # Deduplicate
    if not args.no_dedup and len(all_papers) > 1:
        before = len(all_papers)
        all_papers = deduplicate(all_papers)
        print(f"[*] Dedup: {before} → {len(all_papers)} unique papers", file=sys.stderr)

    # Trim to max results
    all_papers = all_papers[:args.max_results]

    # Sort by citations (descending) by default
    all_papers.sort(key=lambda p: p.get("citations", 0), reverse=True)

    # Summary
    summary = build_summary(all_papers, args.query)
    print(f"\n[*] Final: {len(all_papers)} papers | "
          f"Years: {summary['year_range']} | "
          f"Avg citations: {summary['avg_citations']} | "
          f"OA: {summary['open_access_count']}",
          file=sys.stderr)

    # Export
    if args.export == "bibtex":
        output = "\n\n".join(to_bibtex_entry(p, i) for i, p in enumerate(all_papers, 1))
    elif args.export == "markdown":
        output = f"# Search Results: {args.query}\n\n**Summary:** {summary['total']} papers, "
        output += f"{summary['year_range']}, avg {summary['avg_citations']} citations\n\n"
        output += "## Papers\n\n"
        output += to_markdown_table(all_papers)
    elif args.export == "csv":
        output = to_csv(all_papers)
    else:
        # JSON
        result = {
            "summary": summary,
            "papers": [] if args.summary_only else all_papers,
        }
        output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n[OK] Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
