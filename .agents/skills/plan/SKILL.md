---
name: plan
description: Spec, Fable5 LEDGER cards, and Editorial SVG architecture diagrams.
---

# /plan — Specification & Architecture

Plan before code. All output goes to `implementation_plan.md` artifact.

---

## HARD RULES — Every Plan Must Follow These

### Rule 1: Deep-Read Before Proposing
Before writing any [MODIFY] section, you MUST:
1. `view_file` the target file and READ the actual current code.
2. `houmi_graft_intel(action="skeleton")` to list the file's exported API.
3. `houmi_graft_intel(action="callers")` to check what depends on symbols you're changing.
4. If renaming or deleting: run blast radius check on every affected symbol.

**NEVER propose changes based on assumption. Read first, plan second.**

### Rule 2: Every [MODIFY] Section Must Have 4 Parts

```markdown
#### [MODIFY] [filename](file:///absolute/path#Lstart-Lend)

**Current State (สภาพปัจจุบัน):**
- What exists right now in the file? Cite exact line numbers and show the relevant code snippet.
- Example: "Line 28: `rotation_deg: number` — already exists on TextBlock interface."

**What Changes (สิ่งที่จะเปลี่ยน):**
- Exact fields/functions/components being added, removed, or modified.
- Show a before → after diff or pseudocode of the change.

**Why This Change (เหตุผล):**
- Why is this change necessary? What problem does it solve?
- What breaks if we DON'T make this change?

**Blast Radius (ผลกระทบ):**
- Which other files import or depend on this symbol?
- Will any existing tests break?
- Does the backend need to be updated too?
```

### Rule 3: Never Say "Ensure X" Without Specifics
❌ BAD: "Ensure `angle?: number` is supported on TextBlock."
✅ GOOD:
> **Current State:** `TextBlock` at [projectStore.ts:L20-55](file:///path#L20-L55) already has `rotation_deg: number` (L28). Missing: `flip_x`, `flip_y`, `transform_origin`.
>
> **What Changes:** Add 3 new optional fields after L54:
> ```typescript
> flip_x?: boolean;        // horizontal mirror
> flip_y?: boolean;        // vertical mirror  
> transform_origin?: [number, number]; // [0-1, 0-1] pivot point for rotation
> ```
>
> **Why:** Canvas rotation presets need flip state. 9-point anchor grid maps to Fabric.js `originX`/`originY` which requires `[0, 0]` to `[1, 1]` range stored on the block.
>
> **Blast Radius:** `updateBlock()` (L127) accepts `Partial<TextBlock>` so new optional fields are backwards-compatible. Canvas.tsx L2831 reads `obj.angle` → must also sync `flip_x`/`flip_y` to `obj.flipX`/`obj.flipY` in `object:modified` handler.

### Rule 4: Break Into LEDGER Cards With Acceptance Tests
Every plan must end with concrete task cards:
```markdown
## LEDGER Cards
- [ ] CARD-01: <title>
  -- accept: <machine-checkable command that proves it's done>
  -- scope: <directory or file affected>
  -- depends: <which card must finish first, if any>
```

Acceptance tests must be MACHINE-CHECKABLE, not "looks right":
- ❌ BAD: `-- accept: verify rotation works`
- ✅ GOOD: `-- accept: cd frontend_rework && npx tsc --noEmit && grep -r "Photoshop" src/ | wc -l | grep "^0$"`

### Rule 5: Check Existing Code Before Adding New Fields
Before proposing new TypeScript interfaces or fields:
1. Search if the field already exists under a different name.
2. Check if `extra_metadata` already stores this data.
3. Verify the backend schema matches — record discrepancies in `houmi_backend_sync`.

---

## Procedure
1. **Research:** `view_file` all target files. Run `houmi_graft_intel(skeleton)` and `houmi_graft_intel(callers)` for every symbol being changed.
2. **Route:** Call `houmi_route(intent="<task>")` to detect required subsystems.
3. **Write Plan:** Create `implementation_plan.md` artifact following Rule 2 format for EVERY modified file.
4. **Diagram:** Generate Editorial SVG via `houmi_diagram` for architecture overview.
5. **Cards:** Break into LEDGER cards via `houmi_ledger(action="add_card")`.
6. **Backend Sync:** Record any new API requirements via `houmi_backend_sync`.
7. **DO NOT write application source code.** Plan only.
