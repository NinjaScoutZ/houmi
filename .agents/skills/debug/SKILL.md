---
name: debug
description: Hypothesis-driven debugging with blast radius analysis and diagnostics.
---

# /debug — Diagnose & Fix

1. Reproduce the error. Check build output or runtime logs.
2. Formulate hypothesis.
3. Check blast radius before fixing: `houmi_graft_intel(action="callers", target="<suspect_symbol>")`.
4. Apply minimal fix within `houmi_guard` write-guard.
5. Verify fix: `houmi_stack_grill(target_path="<changed_file>")`.
