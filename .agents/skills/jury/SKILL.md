---
name: jury
description: Final ship/audit gate. Full compliance checklist before release.
---

# /jury — Ship Audit

Final gate before declaring work complete.

## Checklist
1. All LEDGER cards closed with evidence: `houmi_ledger(action="pop_card")` returns `card: null`.
2. Stack grill passes clean: `houmi_stack_grill` returns `passed: true`.
3. Backend contract is complete: `houmi_backend_sync(action="list_apis")` lists all required commands.
4. No hollow code, no TODOs, no `any` types, no Canvas leaks.
5. Editorial diagram exists in `.agents/diagrams/` documenting final architecture.
