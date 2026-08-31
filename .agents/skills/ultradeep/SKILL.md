---
name: ultradeep
description: 1-Phase deep execution with Write-Guard and Stack Griller.
---

# /ultradeep — Single Phase Execution

Execute exactly one LEDGER card per turn with maximum depth.

## Procedure
1. Pop card: `houmi_ledger(action="pop_card")`.
2. Set write-guard: `houmi_guard(action="set_paths", paths=["<target_files>"])`.
3. Execute production-grade code changes.
4. Grill result: `houmi_stack_grill(target_path="<changed_path>")`.
5. Close card with evidence: `houmi_ledger(action="close_card", args={"card_id": "...", "evidence": "..."})`.
6. End turn: `houmi_guard(action="end_turn")`.
