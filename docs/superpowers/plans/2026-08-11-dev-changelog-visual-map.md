# Dev Changelog & Visual Development Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an append-only Dev Patch recording system, FastAPI backend service, auto-sync to [CHANGELOG.md](file:///e:/houmi/CHANGELOG.md), and an interactive visual flowchart dashboard for Houmi Studio.

**Architecture:** A lightweight Python service (`backend/app/services/dev_patch_service.py`) writes append-only event JSON files under `data/dev_patches/`, aggregates them into `data/dev_changelog.json` & [CHANGELOG.md](file:///e:/houmi/CHANGELOG.md), and exposes REST endpoints via FastAPI (`backend/app/routes/dev_map.py`). A React component (`frontend/src/components/dev_map/DevMapDashboard.tsx`) provides an interactive graph visualization of dev nodes and customer releases.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, React 18, TypeScript, Tailwind CSS, Lucide Icons.

## Global Constraints
- Customer release tags (e.g., `v0.3.1`) are strictly prohibited during ongoing development unless authorized by explicit release flag (`is_customer_release=true`).
- All internal development events are tagged with `Dev` label.
- Data edits are append-only to prevent Git merge conflicts.

---

### Task 1: Dev Patch Data Layer & Service

**Files:**
- Create: `backend/app/services/dev_patch_service.py`
- Test: `backend/tests/test_dev_patch_service.py`

**Interfaces:**
- Consumes: JSON files in `data/dev_patches/`
- Produces: `DevPatch` model, `record_dev_patch()`, `get_dev_history()`, `sync_changelog_markdown()`

- [ ] **Step 1: Write failing unit test for `record_dev_patch` and `get_dev_history`**

Create `backend/tests/test_dev_patch_service.py`:
```python
import pytest
from pathlib import Path
from app.services.dev_patch_service import record_dev_patch, get_dev_history

def test_record_and_read_dev_patch(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.dev_patch_service.PATCHES_DIR", tmp_path / "dev_patches")
    monkeypatch.setattr("app.services.dev_patch_service.MASTER_JSON_PATH", tmp_path / "dev_changelog.json")
    monkeypatch.setattr("app.services.dev_patch_service.CHANGELOG_MD_PATH", tmp_path / "CHANGELOG.md")

    patch_data = {
        "title": "Test Dev Feature",
        "summary": "Added dev patch logging service",
        "component_tags": ["Backend"],
        "changes": [{"category": "Added", "description": "Dev patch service"}]
    }

    record = record_dev_patch(patch_data)
    assert record["version_type"] == "Dev"
    assert "patch_id" in record

    history = get_dev_history()
    assert len(history["nodes"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dev_patch_service.py`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `dev_patch_service.py`**

Create `backend/app/services/dev_patch_service.py`:
```python
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
            lines.append(f"- **{ch.get('category', 'Updated')}**: {ch.get('description', '')}")
        lines.append("\n---\n")

    with open(CHANGELOG_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dev_patch_service.py`
Expected: PASS

---

### Task 2: FastAPI Routes for Dev Map (`/api/dev-map`)

**Files:**
- Create: `backend/app/routes/dev_map.py`
- Modify: `backend/app/main.py:302-319`
- Test: `backend/tests/test_dev_map_routes.py`

**Interfaces:**
- Consumes: `dev_patch_service` functions
- Produces: API Endpoints `GET /api/dev-map/history`, `GET /api/dev-map/context`, `POST /api/dev-map/record`

- [ ] **Step 1: Write failing route integration test**

Create `backend/tests/test_dev_map_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dev_map_routes():
    res = client.get("/api/dev-map/history")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data

    post_res = client.post("/api/dev-map/record", json={
        "title": "API Test Patch",
        "summary": "Testing endpoint",
        "component_tags": ["Test"]
    })
    assert post_res.status_code == 200
    assert post_res.json()["version_type"] == "Dev"
```

- [ ] **Step 2: Run route test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dev_map_routes.py`
Expected: 404 Not Found on `/api/dev-map/history`.

- [ ] **Step 3: Implement `backend/app/routes/dev_map.py` and register in `main.py`**

Create `backend/app/routes/dev_map.py`:
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from app.services.dev_patch_service import get_dev_history, record_dev_patch

router = APIRouter(prefix="/dev-map", tags=["dev-map"])

class ChangeItem(BaseModel):
    category: str = "Updated"
    description: str

class RecordPatchRequest(BaseModel):
    title: str
    summary: Optional[str] = ""
    component_tags: Optional[List[str]] = ["General"]
    author: Optional[str] = "Antigravity AI"
    changes: Optional[List[ChangeItem]] = []
    modified_files: Optional[List[str]] = []
    is_customer_release: Optional[bool] = False
    customer_version: Optional[str] = None
    model_config = ConfigDict(extra="allow")

@router.get("/history")
def get_history():
    return get_dev_history()

@router.get("/context")
def get_recent_context():
    history = get_dev_history()
    nodes = history.get("nodes", [])[:5]
    return {
        "recent_patches": nodes,
        "total": len(history.get("nodes", []))
    }

@router.post("/record")
def record_patch(req: RecordPatchRequest):
    data = req.model_dump()
    return record_dev_patch(data)
```

In `backend/app/main.py`, import and include `dev_map.router`:
```python
from app.routes import dev_map
app.include_router(dev_map.router, prefix="/api")
```

- [ ] **Step 4: Run route test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dev_map_routes.py`
Expected: PASS

---

### Task 3: React Frontend Visual Dev Map Component & Route (`/dev-map`)

**Files:**
- Create: `frontend/src/components/dev_map/DevMapDashboard.tsx`
- Modify: `frontend/src/App.tsx` (add Dev Map tab / route view)

**Interfaces:**
- Consumes: `GET /api/dev-map/history`, `POST /api/dev-map/record`
- Produces: Interactive visual node flowchart & timeline component in React

- [ ] **Step 1: Create `DevMapDashboard.tsx`**

Create `frontend/src/components/dev_map/DevMapDashboard.tsx`:
```tsx
import React, { useEffect, useState } from 'react';
import { GitCommit, Tag, Layers, RefreshCw, CheckCircle, ShieldAlert } from 'lucide-react';

interface DevNode {
  id: string;
  label: string;
  title: string;
  type: string;
  is_customer_release: boolean;
  timestamp: string;
  tags: string[];
  summary: string;
  changes: Array<{ category: string; description: string }>;
  modified_files: string[];
}

export const DevMapDashboard: React.FC = () => {
  const [nodes, setNodes] = useState<DevNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<DevNode | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/dev-map/history');
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes || []);
        if (data.nodes && data.nodes.length > 0) {
          setSelectedNode(data.nodes[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch dev map:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <div className="flex h-full w-full bg-slate-950 text-slate-100 p-6 overflow-hidden">
      {/* Left: Flowchart Timeline Node List */}
      <div className="w-1/2 flex flex-col border-r border-slate-800 pr-6 overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Layers className="text-cyan-400" /> Dev Map & Visual Changelog
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Internal Development Nodes & Release Roadmap
            </p>
          </div>
          <button
            onClick={fetchHistory}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-md text-xs transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>

        {/* Nodes Timeline Tree */}
        <div className="relative border-l-2 border-slate-800 ml-4 pl-6 space-y-6">
          {nodes.map((node) => {
            const isSelected = selectedNode?.id === node.id;
            return (
              <div
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className={`cursor-pointer transition-all p-4 rounded-xl border ${
                  isSelected
                    ? 'border-cyan-500/80 bg-cyan-950/20 shadow-lg shadow-cyan-950/50'
                    : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                      node.is_customer_release
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    }`}
                  >
                    {node.is_customer_release ? <CheckCircle className="w-3 h-3" /> : <GitCommit className="w-3 h-3" />}
                    {node.label}
                  </span>
                  <span className="text-xs text-slate-400">
                    {new Date(node.timestamp).toLocaleString()}
                  </span>
                </div>
                <h3 className="text-base font-semibold mt-2 text-slate-200">{node.title}</h3>
                {node.summary && <p className="text-xs text-slate-400 mt-1 line-clamp-2">{node.summary}</p>}
                
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {node.tags?.map((t, idx) => (
                    <span key={idx} className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-800 text-slate-300 text-[10px] rounded">
                      <Tag className="w-2.5 h-2.5" /> {t}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: Node Details Inspector Pane */}
      <div className="w-1/2 pl-6 flex flex-col overflow-y-auto">
        {selectedNode ? (
          <div>
            <div className="border-b border-slate-800 pb-4 mb-4">
              <span className="text-xs uppercase tracking-wider text-cyan-400 font-mono">
                Patch Inspector ({selectedNode.id})
              </span>
              <h2 className="text-xl font-bold mt-1">{selectedNode.title}</h2>
              <p className="text-xs text-slate-400 mt-1">Author: {selectedNode.author}</p>
            </div>

            {selectedNode.summary && (
              <div className="mb-6 bg-slate-900/80 p-4 rounded-xl border border-slate-800">
                <h4 className="text-xs font-semibold text-slate-300 mb-1">Summary</h4>
                <p className="text-xs text-slate-300 leading-relaxed">{selectedNode.summary}</p>
              </div>
            )}

            <div className="mb-6">
              <h4 className="text-sm font-semibold text-slate-200 mb-3">Recorded Changes</h4>
              <div className="space-y-2">
                {selectedNode.changes?.map((ch, i) => (
                  <div key={i} className="flex gap-2 text-xs bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/80">
                    <span className="font-semibold text-cyan-400 shrink-0">[{ch.category}]</span>
                    <span className="text-slate-300">{ch.description}</span>
                  </div>
                ))}
              </div>
            </div>

            {selectedNode.modified_files?.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-slate-200 mb-2">Modified Files</h4>
                <ul className="text-xs font-mono text-slate-400 space-y-1 bg-slate-900 p-3 rounded-lg border border-slate-800">
                  {selectedNode.modified_files.map((file, i) => (
                    <li key={i} className="truncate">• {file}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <ShieldAlert className="w-8 h-8 mb-2" />
            <p className="text-sm">Select a patch node to inspect details</p>
          </div>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Add route / tab in React App**

Mount `DevMapDashboard` component into `App.tsx` or settings/admin navigation so it is accessible.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-11-dev-changelog-visual-map.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
