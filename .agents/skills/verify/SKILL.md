---
name: verify
description: Run stack griller, build diagnostics, and close LEDGER card with disk evidence.
---

# /verify — Proof & Close

Verify work is complete with machine-checkable evidence.

## Plan Review Verification (when reviewing a plan)
Before approving or presenting a plan, verify:
1. Every [MODIFY] section has: Current State, What Changes, Why, Blast Radius.
2. Every proposed field/type change cites the actual line number from source.
3. No "Ensure X" without specifics.
4. LEDGER cards have machine-checkable acceptance commands.
5. If renaming: blast radius analysis covers all importing files.

## Code Verification (when reviewing implementation)
1. Run stack grill: `houmi_stack_grill(target_path="frontend_rework/src")`.
2. Run build: execute `cd frontend_rework && npm run build` and check exit code.
3. Close card with evidence: `houmi_ledger(action="close_card", args={"card_id": "...", "evidence": "build clean, grill 0 issues"})`.
4. If issues found → do NOT close. Fix first or add new LEDGER card.
