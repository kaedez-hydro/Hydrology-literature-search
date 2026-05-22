#!/usr/bin/env python3
"""
Query optimizer for hydrology × remote sensing literature search.

Converts a natural-language research direction into 3–5 optimized search queries
suitable for Crossref/OpenAlex APIs.

Two modes:
  --local   : Rule-based synonym expansion (default, no API key needed)
  --llm     : LLM-powered intelligent expansion (needs API key)
              Set OPENAI_API_KEY or OPENAI_BASE_URL env vars.

Usage:
    python optimize_query.py "SAR影像用U-Net做洪水淹没提取"
    python optimize_query.py "spatial cross-validation for flood susceptibility" --llm
    python optimize_query.py "flood depth estimation with random forest" --top-k 5 --llm
"""

import argparse
import json
import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── Domain Synonym & Expansion Library ──────────────────────────────────────

# Term → list of alternative search terms
SYNONYM_MAP = {
    "flood": ["flood", "inundation", "flooding", "floodwater", "waterlogging"],
    "inundation": ["inundation", "flood", "submersion", "flood extent", "floodwater extent"],
    "SAR": ["SAR", "synthetic aperture radar", "Sentinel-1", "radar", "TerraSAR-X", "RADARSAT"],
    "Sentinel-1": ["Sentinel-1", "C-band SAR", "SAR", "synthetic aperture radar"],
    "water body": ["water body", "surface water", "open water", "inland water"],
    "water extraction": ["water extraction", "water body extraction", "water mapping", "surface water mapping", "flood mapping"],
    "deep learning": ["deep learning", "neural network", "CNN", "convolutional neural network"],
    "U-Net": ["U-Net", "UNet", "encoder-decoder", "fully convolutional network", "semantic segmentation"],
    "semantic segmentation": ["semantic segmentation", "pixel-wise classification", "image segmentation", "U-Net"],
    "random forest": ["random forest", "RF", "ensemble learning", "tree-based model", "Random Forests"],
    "XGBoost": ["XGBoost", "gradient boosting", "GBM", "extreme gradient boosting"],
    "attention": ["attention mechanism", "transformer", "self-attention", "ViT", "spatial attention"],
    "explainable": ["explainable", "SHAP", "interpretable", "XAI", "feature importance", "saliency"],
    "spatial": ["spatial", "geographic", "geospatial", "spatially explicit"],
    "cross-validation": ["cross-validation", "spatial cross-validation", "block cross-validation", "model evaluation", "validation strategy"],
    "GIS": ["GIS", "Geographic Information System", "spatial analysis"],
    "hydrological model": ["hydrological model", "hydrodynamic model", "hydraulic model", "flood model", "LISFLOOD", "HEC-RAS", "SWAT"],
    "hydrology": ["hydrology", "water resources", "watershed", "catchment", "basin"],
    "precipitation": ["precipitation", "rainfall", "storm", "extreme rainfall", "heavy rain"],
    "climate change": ["climate change", "global warming", "climate variability", "climate projection"],
    "DEM": ["DEM", "digital elevation model", "topography", "terrain", "SRTM"],
    "landslide": ["landslide", "land subsidence", "slope failure", "mass movement"],
}

# Method → common search contexts
METHOD_CONTEXTS = {
    "U-Net": [" U-Net ", " encoder-decoder ", " fully convolutional "],
    "CNN": [" CNN ", " convolutional neural network ", " deep convolutional "],
    "ResNet": [" ResNet ", " residual network ", " ResNet-50 ", " ResNet-34 "],
    "transformer": [" transformer ", " vision transformer ", " Swin transformer "],
    "random forest": [" random forest ", " Random Forests ", " RF "],
    "XGBoost": [" XGBoost ", " gradient boosting ", " extreme gradient boosting "],
    "LSTM": [" LSTM ", " long short-term memory ", " recurrent neural network "],
    "GAN": [" GAN ", " generative adversarial network ", " adversarial training "],
}

# Chinese → English term mapping (hydrology × RS × ML domain)
ZH_EN_MAP = {
    "洪水": "flood",
    "淹没": "inundation",
    "洪涝": "flood",
    "内涝": "urban flooding",
    "降雨": "precipitation",
    "暴雨": "extreme rainfall",
    "径流": "runoff",
    "流域": "watershed",
    "河网": "river network",
    "河道": "river channel",
    "蓄滞洪": "flood detention",
    "蓄滞洪区": "flood storage area",
    "洼地": "lowland",
    "平原": "plain",
    "地形": "terrain",
    "高程": "digital elevation model",
    "遥感": "remote sensing",
    "卫星": "satellite",
    "影像": "imagery",
    "图像": "image",
    "制图": "mapping",
    "提取": "extraction",
    "检测": "detection",
    "分割": "segmentation",
    "分类": "classification",
    "变化检测": "change detection",
    "深度学习": "deep learning",
    "机器学习": "machine learning",
    "神经网络": "neural network",
    "卷积": "convolutional",
    "语义分割": "semantic segmentation",
    "代理模型": "surrogate model",
    "替代模型": "surrogate model",
    "水动力": "hydrodynamic",
    "水文": "hydrology",
    "水动力模型": "hydrodynamic model",
    "数值模拟": "numerical simulation",
    "空间自相关": "spatial autocorrelation",
    "空间异质性": "spatial heterogeneity",
    "空间划分": "spatial partitioning",
    "空间验证": "spatial validation",
    "交叉验证": "cross-validation",
    "泛化": "generalization",
    "随机森林": "random forest",
    "支持向量机": "support vector machine",
    "可解释性": "explainable AI",
    "消融": "ablation",
    "精度": "accuracy",
    "不确定性": "uncertainty",
    "灾情": "disaster",
    "灾害": "hazard",
    "风险": "risk",
    "气候变化": "climate change",
    "土地利用": "land use",
    "土壤": "soil moisture",
    "蒸散发": "evapotranspiration",
    "复合": "compound",
    "沿海": "coastal",
    "潮汐": "tidal",
    "patch": "patch",
    "patch-based": "patch-based",
    "栅格": "raster",
    "全流域": "basin-scale",
    "大清河": "Daqing River",
    "海河": "Haihe River",
}

# Domain-specific seed terms to always try
DOMAIN_FILLERS = {
    "remote_sensing": ["remote sensing", "satellite", "Earth observation", "aerial imagery"],
    "hydrology": ["hydrology", "water resources", "watershed", "catchment"],
    "flood": ["flood", "inundation", "flood hazard", "flood risk"],
    "method": ["deep learning", "machine learning", "neural network", "data-driven"],
}


def expand_term(term_lower):
    """Return list of alternative terms for a given keyword."""
    for key, synonyms in SYNONYM_MAP.items():
        if key.lower() in term_lower or term_lower in key.lower():
            return synonyms
    return [term_lower]


def extract_keywords_mixed(text):
    """
    Extract keywords from mixed Chinese-English text.
    Returns list of English search terms, grouped by category.
    """
    import re
    keywords = []
    
    # 1. Extract known multi-word English phrases first (greedy, longest match)
    KNOWN_PHRASES = [
        "attention mechanism", "deep learning", "machine learning", "remote sensing",
        "random forest", "neural network", "semantic segmentation", "change detection",
        "water body", "water body extraction", "water extraction", "flood mapping",
        "flood extent", "flood hazard", "flood risk", "flood susceptibility",
        "cross validation", "spatial cross-validation", "spatial cross validation",
        "block cross-validation", "earth observation", "land use", "land cover",
        "support vector machine", "digital elevation model", "digital elevation",
        "synthetic aperture radar", "convolutional neural network", "fully convolutional",
        "vision transformer", "swin transformer", "spatial autocorrelation",
        "spatial heterogeneity", "spatial validation", "compound flooding",
        "extreme rainfall", "surface water", "water resources", "climate change",
        "numerical simulation", "hydrodynamic model", "surrogate model",
        "explainable AI", "feature importance", "image segmentation",
        "synthetic aperture", "object detection", "semantic segmentation",
        "instance segmentation", "transfer learning", "data assimilation",
        "time series", "real-time", "near real-time", "early warning",
        "uncertainty quantification", "ensemble learning", "gradient boosting",
    ]
    
    text_lower = text.lower()
    for phrase in sorted(KNOWN_PHRASES, key=len, reverse=True):
        if phrase in text_lower:
            keywords.append(phrase)
            text_lower = text_lower.replace(phrase, " ", 1)

    # 2. Extract remaining English words (filter noise)
    NOISE_WORDS = {"with", "using", "for", "and", "the", "of", "in", "on", "to",
                   "a", "an", "is", "are", "was", "from", "by", "as", "at",
                   "that", "this", "can", "has", "have", "its", "it", "or",
                   "be", "no", "not", "but", "if", "so", "we", "they", "their",
                   "some", "all", "each", "any", "more", "most", "only", "also",
                   "new", "based", "use", "used", "make", "made", "get", "got",
                   "need", "needs", "way", "how", "what", "when", "where", "which",
                   "approach", "method", "model", "study", "research", "analysis",
                   "paper", "result", "data", "work", "show", "shown", "find",
                   "found", "propose", "proposed", "apply", "applied",
                   "mechanism", "mechanisms", "framework", "technique",
                   "different", "various", "several", "many", "better",
                   "process", "system", "application", "applications",
                   "provide", "provided", "present", "presented"}
    
    remaining = re.findall(r'[A-Za-z][A-Za-z0-9\-]*', text_lower)
    # Filter out noise and short fragments, keep acronyms (SAR, DEM, GIS, etc.)
    for w in remaining:
        wl = w.lower()
        if wl in NOISE_WORDS:
            continue
        if len(w) <= 2 and w.upper() != w:  # skip short non-acronyms
            continue
        # Don't duplicate if already captured as part of a phrase
        if wl not in " ".join(keywords):
            keywords.append(w)

    # 3. Translate Chinese terms
    chinese_clean = re.sub(r'[\s\.,;:!?\(\)\[\]{}""''，。；：！？（）【】《》""'']+', '', text)
    chinese_only = re.sub(r'[A-Za-z0-9\-]+', '', chinese_clean)
    for zh_term, en_term in sorted(ZH_EN_MAP.items(), key=lambda x: -len(x[0])):
        if zh_term in chinese_only:
            if en_term not in keywords:
                keywords.append(en_term)
            chinese_only = chinese_only.replace(zh_term, " ", 1)

    # 4. Expand via synonym dictionary
    expanded = []
    for kw in keywords:
        synonyms = expand_term(kw)
        # Take the original + up to 2 synonyms
        if kw in synonyms:
            synonyms.remove(kw)
        expanded.append(kw)
        expanded.extend(synonyms[:2])
    
    # Deduplicate
    seen = set()
    result = []
    for t in expanded:
        tl = t.lower()
        if tl not in seen and len(t) > 2:
            seen.add(tl)
            result.append(t)
    
    return result


def generate_local_queries(description, top_k=5):
    """
    Compose search queries by picking terms from different semantic categories:
    method/tool, application/phenomenon, data/sensor, domain context.
    """
    all_terms = extract_keywords_mixed(description)
    
    # Categorize terms
    METHOD_SIGNALS = {"u-net", "unet", "cnn", "convolutional", "resnet", "transformer",
                      "deep learning", "neural network", "attention", "lstm", "gan",
                      "random forest", "xgboost", "svm", "gradient boosting",
                      "encoder-decoder", "segmentation", "classification",
                      "semantic segmentation", "transfer learning", "ensemble",
                      "explainable", "shap", "feature importance"}
    SENSOR_SIGNALS = {"sar", "sentinel-1", "sentinel-2", "landsat", "modis",
                      "terrasar-x", "radarsat", "optical", "multispectral",
                      "hyperspectral", "radar", "synthetic aperture", "c-band",
                      "x-band", "uav", "drone", "aerial", "srtm", "lidar"}
    APP_SIGNALS = {"flood", "inundation", "flooding", "water body", "water extraction",
                   "surface water", "drought", "runoff", "precipitation", "rainfall",
                   "landslide", "erosion", "evapotranspiration", "soil moisture",
                   "land use", "land cover", "water quality", "snow", "glacier",
                   "groundwater", "subsidence"}
    
    methods = [t for t in all_terms if t.lower() in METHOD_SIGNALS]
    sensors = [t for t in all_terms if t.lower() in SENSOR_SIGNALS]
    apps = [t for t in all_terms if t.lower() in APP_SIGNALS]
    # Anything else: general domain terms
    other = [t for t in all_terms if t not in methods and t not in sensors and t not in apps]
    
    # Add domain fillers if categories are sparse
    if not sensors:
        sensors = ["remote sensing", "satellite"]
    if not apps:
        apps = ["hydrology", "water resources"]
    
    queries = []
    
    # Q1: method + application + sensor (most specific)
    q1 = methods[:2] + apps[:1] + sensors[:1]
    queries.append(" ".join(q1))
    
    # Q2: method-focused (for finding similar method papers)
    if len(methods) >= 2:
        queries.append(" ".join(methods[:3] + apps[:1]))
    
    # Q3: application + sensor (broader, higher recall)
    queries.append(" ".join(apps[:2] + sensors[:1] + methods[:1]))
    
    # Q4: alternate method angle (if we have synonyms)
    if len(methods) >= 3:
        queries.append(" ".join(methods[1:4] + apps[:1]))
    
    # Q5: review angle
    queries.append(" ".join(methods[:1] + apps[:1] + sensors[:1] + ["review"]))
    
    # Q6: another sensor angle
    if len(sensors) >= 2:
        queries.append(" ".join(sensors[:2] + apps[:1] + methods[:1]))
    
    # Normalize and deduplicate
    normalized = []
    seen_q = set()
    for q in queries:
        q_clean = " ".join(q.split()).strip().lower()
        if q_clean not in seen_q and len(q_clean.split()) >= 3:
            seen_q.add(q_clean)
            normalized.append(q_clean)
    
    return normalized[:top_k]


# ─── LLM-Powered Optimization ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a research librarian specializing in hydrology, remote sensing, and machine learning. Your task is to convert a researcher's natural-language description of a research topic into 3–5 optimized search queries for academic databases (Crossref, OpenAlex).

Each query should:
1. Use different keyword combinations and synonyms to maximize recall
2. Include standardized technical terms from hydrology, remote sensing, or ML as appropriate
3. Be 4–8 words, concise, no punctuation
4. Cover different angles: (a) method-focused, (b) application-focused, (c) data/sensor-focused, (d) broad review, (e) problem-focused
5. Use English only

For each query, explain in one short sentence why this angle was chosen.

Output format (JSON only):
{
  "queries": [
    {"query": "...", "angle": "short explanation"},
    ...
  ]
}

Domain guidance:
- Flood terms: flood, inundation, flooding, floodwater, flood extent, flood hazard
- SAR terms: SAR, Sentinel-1, synthetic aperture radar, TerraSAR-X, radar
- DL terms: deep learning, CNN, U-Net, transformer, semantic segmentation, neural network
- Hydrology terms: hydrology, water resources, watershed, catchment, basin, floodplain
- Validation terms: cross-validation, spatial cross-validation, block cross-validation, accuracy assessment
- Remote sensing: remote sensing, satellite imagery, Earth observation, multispectral
"""


def generate_llm_queries(description, top_k=5, base_url=None, api_key=None, model=None):
    """Use an LLM to intelligently expand a research direction into search queries."""
    base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print("ERROR: No API key. Set OPENAI_API_KEY env var or pass --api-key.")
        print("Falling back to --local mode.")
        return generate_local_queries(description, top_k)

    try:
        import requests
    except ImportError:
        print("ERROR: requests not installed. Run: pip install requests")
        return generate_local_queries(description, top_k)

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Research topic: {description}"},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        queries = result.get("queries", [])
        return [q["query"] for q in queries[:top_k]]
    except json.JSONDecodeError:
        print("WARNING: LLM returned non-JSON. Falling back to --local mode.")
        return generate_local_queries(description, top_k)
    except Exception as e:
        print(f"WARNING: LLM call failed ({e}). Falling back to --local mode.")
        return generate_local_queries(description, top_k)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hydrology × Remote Sensing query optimizer — "
                    "converts research idea into optimized search queries."
    )
    parser.add_argument("description", nargs="?", help="Research topic in natural language")
    parser.add_argument("--llm", action="store_true", help="Use LLM for intelligent expansion")
    parser.add_argument("--local", action="store_true", default=True,
                        help="Use rule-based synonym expansion (default)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of queries (default: 5)")
    parser.add_argument("--api-key", help="OpenAI-compatible API key (or set OPENAI_API_KEY)")
    parser.add_argument("--base-url", help="API base URL (or set OPENAI_BASE_URL)")
    parser.add_argument("--model", help="Model name (or set OPENAI_MODEL, default: gpt-4o-mini)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    description = args.description
    if not description:
        description = input("Enter your research topic: ").strip()
    if not description:
        print("ERROR: No research topic provided.")
        sys.exit(1)

    print(f"🔍 Research topic: {description}")
    print(f"   Mode: {'LLM' if args.llm else 'Local (synonym expansion)'}")
    print()

    if args.llm:
        queries = generate_llm_queries(
            description, args.top_k, args.base_url, args.api_key, args.model
        )
    else:
        queries = generate_local_queries(description, args.top_k)

    if args.json:
        print(json.dumps({"queries": queries}, ensure_ascii=False, indent=2))
    else:
        print("📋 Optimized search queries:")
        print("=" * 60)
        for i, q in enumerate(queries, 1):
            print(f"  [{i}] {q}")
        print("=" * 60)
        print()
        print("Usage: Copy any query above and run:")
        print('  python scripts/search.py --query "<query>" --max-results 20')
        print()
        if not args.llm:
            print("💡 Tip: Use --llm for smarter query generation (needs OPENAI_API_KEY)")


if __name__ == "__main__":
    main()
