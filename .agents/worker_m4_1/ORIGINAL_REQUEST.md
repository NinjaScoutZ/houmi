## 2026-07-27T10:10:53Z
<USER_REQUEST>
You are Worker 4 implementing Milestone 4 (R4: Advanced Layer Manager Panel & Workspace Productivity) for Houmi Manga Translator.
Your working directory is e:\houmi\.agents\worker_m4_1.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Requirements for R4:
1. Layer Panel List (`frontend/src/App.tsx` sidebar):
   - Display a clean list of text blocks for the active page.
2. Layer Visibility & Lock Toggles:
   - Add Visibility Toggle (Eye icon button per layer item) to toggle layer visibility (visible/hidden).
   - Add Lock Toggle (Lock icon button per layer item) to lock/unlock layer from accidental editing or moving on canvas.
3. Z-Index Reordering:
   - Add Z-Index controls (Bring Forward / Send Backward / Bring to Front / Send to Back) in layer list item actions and context menus to reorder block Z-index layer stack.
4. Quick Focus & Select on Canvas:
   - Clicking a layer item in the list selects that block (`setSelectedBlock`) and pans/centers the canvas viewport smoothly to bring the block into focus.

Verification required:
1. Run `npm --prefix frontend run build` (verify 0 errors).
2. Run `npm --prefix frontend test -- --run` (verify frontend unit tests pass).

Write report to `e:\houmi\.agents\worker_m4_1\changes.md` and handoff to `e:\houmi\.agents\worker_m4_1\handoff.md`. Communicate completed status via send_message.
</USER_REQUEST>
