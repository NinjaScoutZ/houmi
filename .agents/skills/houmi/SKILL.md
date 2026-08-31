---
name: houmi
description: Master Houmi Auto-Detect Intelligence (Auto-routes Canvas, Backend Sync, Editorial Diagrams, Stack Grilling, and Marathon Loop).
---

# Houmi — Master Auto-Detect (`/houmi`)

Single entry-point. Detects what the task needs and activates the right subsystems automatically.

## Auto-Detect Pipeline
1. Call `houmi_route(intent="<user request>")` to classify mode and subsystems.
2. If Canvas/Fabric.js is involved → auto-inspect event listeners & dispose cleanup.
3. If Backend/Tauri IPC is mentioned → auto-record contract to `.agents/backend_requirements.md`.
4. If architecture diagram is needed → generate Editorial SVG via `houmi_diagram` (not Mermaid).
5. If refactor/rename → auto-check blast radius via `houmi_graft_intel.callers`.
6. Always auto-grill on finish via `houmi_stack_grill`.

## Plan Quality Standard (Mandatory for /plan and /ultradeep)

When creating plans or modifying files, ALWAYS follow this standard:

### For Every [MODIFY] Section:
1. **Current State** — Read and cite the actual code (file:line). Never guess.
2. **What Changes** — Show before→after diff or exact additions/deletions.
3. **Why** — Explain the reason. What breaks without this change?
4. **Blast Radius** — List every file that imports/uses the changed symbol.

### Anti-Patterns (NEVER DO):
- ❌ "Ensure X is supported" without reading if X already exists
- ❌ "Add rotation support" without checking `rotation_deg` already exists at L28
- ❌ One-liner [MODIFY] sections with no context
- ❌ Proposing new fields without checking `extra_metadata` for duplicates

### Quality Gate:
Before presenting a plan to the user, self-check:
- Can a developer who never saw this codebase understand EXACTLY what to do from reading the plan alone?
- Does every [MODIFY] section cite actual line numbers from `view_file`?
- Are there machine-checkable acceptance tests for every LEDGER card?

If the answer to any of these is NO, the plan is not ready. Go deeper.

## MCP Tool Reference
All tools live on `ServerName="houmi-core"`:

| Tool | Purpose |
|---|---|
| `houmi_route` | Auto-detect intent → recommended mode & subsystem triggers |
| `houmi_ledger` | Fable5 task cards: init, pop_card, add_card, close_card (evidence required) |
| `houmi_backend_sync` | Record/list Tauri IPC & REST API contracts |
| `houmi_stack_grill` | Scan for Type any, Canvas leaks, hardcoded colors, hollow code |
| `houmi_graft_intel` | Symbol callers (blast radius) and file skeleton (API at a glance) |
| `houmi_diagram` | Editorial SVG architecture diagrams (Dark Obsidian / Minimal Light) |
| `houmi_guard` | Write-guard path allowlisting per phase |
