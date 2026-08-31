---
name: loop
description: Autonomous marathon loop (6-8 hours). Executes LEDGER cards, self-grills, expands backlog, and auto-wakes continuously.
---

# /loop — Autonomous Marathon

Continuous self-driving development cycle. Runs until all LEDGER cards are done or time limit is reached.

## The Perpetual Cycle

```text
┌─────────────────────────────────────────────────────────┐
│ 1. POP — houmi_ledger(action="pop_card")                │
│    Get highest-priority open card from disk.             │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│ 2. EXECUTE — Write production code in frontend_rework/  │
│    Follow frontend-design + antigravity-design standards │
│    If backend function needed → houmi_backend_sync       │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│ 3. GRILL — houmi_stack_grill + adversarial self-check   │
│    Attack: Type any? Canvas leaks? Hollow code? UX?     │
│    If defects found → add new cards to LEDGER            │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│ 4. CLOSE — houmi_ledger(action="close_card") w/evidence │
│    Evidence = build output + grill results               │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│ 5. WAKE — schedule(DurationSeconds=2, Prompt=           │
│    "LOOP PULSE: pop next card, execute, grill, close")  │
│    Loop back to Step 1 immediately.                      │
└─────────────────────────────────────────────────────────┘
```

## Termination
- All LEDGER cards closed + grill returns 0 critical issues.
- User sends `/stop` or cancels the schedule task.
