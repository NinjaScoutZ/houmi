# Specification: Dev Changelog & Visual Development Map System

**Date**: 2026-08-11  
**Project**: Houmi Studio (`e:\houmi`)  
**Status**: Approved / In Design Review  

---

## 1. Overview & Objectives

The **Dev Changelog & Visual Development Map System** is a real-time development tracking, patch recording, and interactive visualization platform for Houmi Studio. It serves as the single source of truth for all code edits, feature additions, and version progressions.

### Key Rules & Constraints
1. **Direct Patching Workflow**: Every task or feature completion is packaged and recorded as a patch.
2. **Strict Customer Version Locking**: Customer-facing release version tags (e.g., `v0.3.1`, `v0.3.5`) are strictly locked and prohibited during ongoing development. Only when the user explicitly declares a release as a "Customer Release Patch" can an official version tag be applied.
3. **Internal `Dev` Tagging**: All ongoing work is tagged under the `Dev` label (e.g., `Dev-20260811-0222` or `Dev-Patch-xxx`).
4. **Bi-directional AI Integration**: AI (Antigravity) can read the development context (`/graft` + `/api/dev-map/context`) and automatically record structured work logs upon completing each task.
5. **Interactive Visual Map**: A web dashboard displaying a visual flowchart graph of Dev nodes, component tags, and release milestones.

---

## 2. System Architecture & Components

```
+-----------------------------------------------------------------------+
|                            AI Agent / Developer                      |
|  - Reads context via /graft & GET /api/dev-map/context                |
|  - Emits Dev Patch event upon completing tasks                        |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                   Phase 1: Core Data Layer (Backend)                  |
|                                                                       |
|  [data/dev_patches/dev-*.json]  <--->  [backend/app/routes/dev_map.py] |
|            (Append-Only)                        |                     |
|                                                 v                     |
|                                    [data/dev_changelog.json]          |
|                                                 |                     |
|                                                 v                     |
|                                          [CHANGELOG.md]               |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                    Phase 2: Visual Dashboard (Frontend)               |
|                                                                       |
|  React Component (/dev-map) <--- WebSocket / REST ---> FastAPI Router |
|  - Interactive Flowchart Node Graph (Nodes & Edges)                   |
|  - Work Log Timeline & Component Filters                             |
|  - Customer Release Promotion Modal                                   |
+-----------------------------------------------------------------------+
```

---

## 3. Data Storage & Schema Design

To prevent Git merge conflicts during concurrent AI updates, dev patches are written as append-only event files under `data/dev_patches/` and aggregated into `data/dev_changelog.json` & `CHANGELOG.md`.

### 3.1 Dev Patch Event Schema (`data/dev_patches/dev-YYYYMMDD-HHMMSS.json`)
```json
{
  "patch_id": "dev-20260811-022200",
  "version_type": "Dev",
  "version_label": "Dev (2026-08-11 02:22)",
  "is_customer_release": false,
  "timestamp": "2026-08-11T02:22:00+07:00",
  "author": "Antigravity AI",
  "title": "Add Dev Map Data Schema and FastAPI Routes",
  "component_tags": ["DevMap", "Backend", "FastAPI"],
  "summary": "Created initial JSON schema, append-only logger, and REST endpoints for dev tracking.",
  "changes": [
    {
      "category": "Added",
      "description": "Created data/dev_patches directory and dev_map FastAPI router."
    },
    {
      "category": "Fixed",
      "description": "Resolved version conflict policy checking."
    }
  ],
  "modified_files": [
    "backend/app/routes/dev_map.py",
    "data/dev_changelog.json",
    "CHANGELOG.md"
  ]
}
```

### 3.2 Master Changelog Aggregator (`data/dev_changelog.json`)
Aggregates all patch event files into an ordered graph node list with parent-child node pointers for visual flowchart rendering.

---

## 4. Backend API Endpoints (`backend/app/routes/dev_map.py`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dev-map/history` | Fetches full list of Dev patches, customer releases, and node edge connections. |
| `GET` | `/api/dev-map/context` | Returns recent 5 Dev patches formatted for AI context injection. |
| `POST` | `/api/dev-map/record` | Endpoint for AI / developer to record a new Dev patch event. |
| `POST` | `/api/dev-map/promote-release` | Admin endpoint to combine pending Dev patches into an official Customer Release (e.g. `v0.2.0`). Requires explicit user parameter. |
| `GET` | `/api/dev-map/export-markdown` | Re-generates `CHANGELOG.md` from master `dev_changelog.json`. |

---

## 5. Frontend Visual Flowchart (`/dev-map`)

### Features
1. **Interactive Node Graph**: Renders nodes (Dev Patches vs Customer Releases) with connecting edge lines indicating progression.
2. **Node Details Inspector Side-Pane**: Clicking any node opens a right drawer displaying summary, changed files, author, and component tags.
3. **Filter & Search Bar**: Filter by Component (`Backend`, `Frontend`, `Smart Balloon`, `OCR`), Status (`Dev` vs `Customer Release`), or search text.
4. **Real-time Live Sync**: Connects to `/ws/telemetry` or polling to update graph nodes live when a new patch is recorded.
5. **Customer Release Promotion Modal**: Protected UI modal to promote accumulative `Dev` patches into a customer-facing version tag upon user authorization.

---

## 6. Implementation Phases

### Phase 1: Core Data Layer & AI Recording (Immediate)
1. Create `data/dev_patches/` directory and `backend/app/routes/dev_map.py`.
2. Implement JSON schema validator and auto-sync logic to update [CHANGELOG.md](file:///e:/houmi/CHANGELOG.md).
3. Mount `dev_map.py` router in `backend/app/main.py`.
4. Test AI recording and context retrieval APIs.

### Phase 2: Web Dashboard & Flowchart UI
1. Create `frontend/src/components/dev_map/DevMapDashboard.tsx`.
2. Add `/dev-map` route in React Frontend and FastAPI fallback.
3. Implement Node Flowchart visualization and Inspector Pane.
4. Connect live WebSocket event listener.

---

## 7. Verification & Acceptance Criteria

- **Verification 1**: AI can post a new Dev Patch via `POST /api/dev-map/record` and verify that `data/dev_patches/` contains the file, `data/dev_changelog.json` is updated, and [CHANGELOG.md](file:///e:/houmi/CHANGELOG.md) contains the entry under `Dev`.
- **Verification 2**: `GET /api/dev-map/history` returns structured nodes and edges correctly.
- **Verification 3**: Customer release tags cannot be created without explicit `is_customer_release: true` flag authorized by user.
