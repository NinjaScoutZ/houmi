import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger("dev-patch-service")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"
PATCHES_DIR = DATA_DIR / "dev_patches"
MASTER_JSON_PATH = DATA_DIR / "dev_changelog.json"
CHANGELOG_MD_PATH = BASE_DIR / "CHANGELOG.md"

def ensure_directories():
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)

def record_dev_patch(patch_input: Dict[str, Any]) -> Dict[str, Any]:
    ensure_directories()
    tz_bkk = timezone(timedelta(hours=7))
    now = datetime.now(tz_bkk)
    timestamp_str = now.isoformat()
    date_str = now.strftime("%Y%m%d-%H%M%S")
    
    is_customer_release = patch_input.get("is_customer_release", False)
    customer_version = patch_input.get("customer_version")

    if is_customer_release and customer_version:
        version_label = f"v{customer_version.lstrip('v')}"
        version_type = "Customer Release"
    else:
        version_label = f"Dev ({now.strftime('%Y-%m-%d %H:%M')})"
        version_type = "Dev"

    patch_id = f"{'release' if is_customer_release else 'dev'}-{date_str}"
    
    patch_record = {
        "patch_id": patch_id,
        "version_type": version_type,
        "version_label": version_label,
        "is_customer_release": is_customer_release,
        "timestamp": timestamp_str,
        "author": patch_input.get("author", "Antigravity AI"),
        "title": patch_input.get("title", "Development Update"),
        "component_tags": patch_input.get("component_tags", ["General"]),
        "summary": patch_input.get("summary", ""),
        "changes": patch_input.get("changes", []),
        "modified_files": patch_input.get("modified_files", [])
    }

    patch_file = PATCHES_DIR / f"{patch_id}.json"
    with open(patch_file, "w", encoding="utf-8") as f:
        json.dump(patch_record, f, ensure_ascii=False, indent=2)

    aggregate_and_sync()
    return patch_record

def get_dev_history() -> Dict[str, Any]:
    ensure_directories()
    patches = []
    if PATCHES_DIR.exists():
        for p_file in sorted(PATCHES_DIR.glob("*.json"), reverse=True):
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    patches.append(json.load(f))
            except Exception as e:
                logger.warning("Failed to read patch file %s: %s", p_file, e)

    nodes = []
    edges = []
    for i, p in enumerate(patches):
        node_id = p["patch_id"]
        nodes.append({
            "id": node_id,
            "label": p["version_label"],
            "title": p["title"],
            "type": p["version_type"],
            "is_customer_release": p["is_customer_release"],
            "timestamp": p["timestamp"],
            "tags": p["component_tags"],
            "summary": p["summary"],
            "changes": p["changes"],
            "modified_files": p["modified_files"]
        })
        if i < len(patches) - 1:
            edges.append({
                "from": patches[i+1]["patch_id"],
                "to": node_id
            })

    return {
        "total_patches": len(patches),
        "nodes": nodes,
        "edges": edges
    }

def aggregate_and_sync():
    history = get_dev_history()
    with open(MASTER_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    sync_to_markdown(history)

def sync_to_markdown(history: Dict[str, Any]):
    lines = ["# Houmi Version Changelog\n"]
    for node in history["nodes"]:
        lines.append(f"## [{node['label']}] - {node['timestamp'][:10]}")
        lines.append(f"**Title**: {node['title']}")
        if node["summary"]:
            lines.append(f"*{node['summary']}*\n")
        
        lines.append("### Changes")
        for ch in node.get("changes", []):
            if isinstance(ch, dict):
                lines.append(f"- **{ch.get('category', 'Updated')}**: {ch.get('description', '')}")
            else:
                lines.append(f"- **Updated**: {ch}")
        lines.append("\n---\n")

    with open(CHANGELOG_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
