# HOUMI AGENT LAW & RULES

**MODE:** self-pilot + HOUMI CORE  
**VOICE:** hard gates · thin boxes · zero hollow code · verified evidence  
**KERNEL:** `houmi-core` MCP + Fable5 Discipline + Graft Intel + Editorial Diagrams  

---

## 0. Hard Law (กฎเหล็ก)

1. **Turn Start (Auto-Route):** Every session/turn MUST begin by calling `houmi_route(intent="...")` on `houmi-core` to auto-detect mode, subsystems (Canvas, Backend, Diagrams), and execution pipeline.
2. **Plan Gate (Fable5):** No code is written before reading actual code and creating LEDGER cards via `houmi_ledger(action="add_card", args={"card_text": "...", "accept_cmd": "..."})`.
3. **Deep Read First:** `view_file` actual source files and run `houmi_graft_intel(action="skeleton")` before proposing any changes. Never guess.
4. **Blast Radius (Graft):** Check dependencies via `houmi_graft_intel(action="callers", target="<symbol>")` before renaming or refactoring.
5. **Write Guard:** Lock modification paths via `houmi_guard(action="set_paths", paths=["..."])` during execution, and call `houmi_guard(action="end_turn")` when done.
6. **Backend Contract Sync:** Whenever frontend requires a new Tauri IPC command or API, immediately record it via `houmi_backend_sync(action="record_api", ...)`.
7. **Editorial Diagrams:** Architecture visuals must use `houmi_diagram` (Editorial SVG Dark Obsidian style) instead of generic Mermaid boxes.
8. **Stack Griller:** On every code change, execute `houmi_stack_grill(target_path="...")` to verify 0 Type `any`, 0 Canvas memory leaks, and 0 token bypasses.
9. **Evidence on Close:** A card in `.agents/LEDGER.md` CANNOT be marked done without concrete machine test evidence via `houmi_ledger(action="close_card", args={"card_id": "...", "evidence": "..."})`.
10. **Marathon Loop:** In `/loop` mode, continuously pop cards, execute, grill, close with evidence, and schedule auto-wake via `schedule(DurationSeconds=2)`.
11. **Distribution Isolation:** `build_patch.py` MUST strictly exclude `frontend/src`, `tests/`, `scripts/`, `google_credentials/`, `.env`, and database files. Only compiled `dist/` and clean client runtimes are packaged.
12. **Docker Host Sync:** Updates to `houmi.click` require `docker compose up -d --build host-api` (with volume mount) rather than restarting `houmi-cloudflared`.

---

## 1. Slash Commands & MCP Routing

| Command | Mode | Required Tool Sequence |
|---|---|---|
| `/houmi` | Auto-Detect Master | `houmi_route` ➔ `houmi_ledger.pop_card` ➔ execute ➔ `houmi_stack_grill` ➔ `houmi_ledger.close_card` |
| `/loop` | Autonomous Marathon | Perpetual cycle: pop card ➔ execute ➔ grill ➔ close w/ evidence ➔ `schedule(2s)` |
| `/plan` | Plan & Spec | `houmi_route` ➔ `view_file` ➔ `houmi_diagram` ➔ `houmi_ledger.add_card` ➔ `houmi_backend_sync` |
| `/ask` | Read-Only Intel | `houmi_graft_intel(skeleton)` ➔ `houmi_graft_intel(callers)` ➔ cite exact file:line |
| `/debug` | Diagnostics & Fix | `houmi_diagnostics` ➔ `houmi_canvas(inspect)` ➔ `houmi_graft_intel(callers)` ➔ fix ➔ grill |
| `/ultradeep` | 1-Phase Execution | `houmi_ledger.pop_card` ➔ `houmi_guard.set_paths` ➔ edit ➔ `houmi_stack_grill` ➔ `houmi_guard.end_turn` |
| `/view` | Architecture Study | `view_file` (full read) ➔ `houmi_graft_intel` ➔ `houmi_diagram` |
| `/verify` | Proof & Close | `houmi_diagnostics` ➔ `houmi_stack_grill` ➔ `houmi_ledger.close_card` (with evidence) |
| `/jury` | Final Ship Audit | All cards complete? Grill 0 issues? Backend contract complete? |

---

## 2. MCP Host Configuration
- Server Name: `houmi-core`
- Tools: `houmi_route`, `houmi_ledger`, `houmi_backend_sync`, `houmi_stack_grill`, `houmi_graft_intel`, `houmi_diagnostics`, `houmi_canvas`, `houmi_diagram`, `houmi_guard`
