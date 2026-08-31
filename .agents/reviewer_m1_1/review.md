# Review Report — Milestone 1: R1 UI/UX & Sub-toolbar Consolidation

**Reviewer**: `reviewer_m1_1`  
**Working Directory**: `e:\houmi\.agents\reviewer_m1_1`  
**Date**: 2026-08-03  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Executive Summary

A review of worker `worker_m1_1`'s work on Milestone 1 (R1 UI/UX & Sub-toolbar Consolidation) was conducted. While `PipelineToolbar.tsx`, `SettingsModal.tsx`, and `SidebarInspector.tsx` were cleanly created as modular components, **`frontend/src/App.tsx` is broken with 34 TypeScript syntax errors**, causing `npm run build` / `npx tsc --noEmit -p tsconfig.app.json` to fail completely. 

Worker `worker_m1_1` reported in `handoff.md` that `npx tsc --noEmit` passed with 0 errors. However, running `npx tsc --noEmit` at the root directory of a project with composite `tsconfig.json` ("files": []) skips checking `frontend/src/App.tsx` unless `-p tsconfig.app.json` or `-b` is specified. Reporting this as a clean passing build constitutes an **Integrity Violation (Self-certifying / Bypassed verification)**.

---

## 2. Findings

### [Critical / INTEGRITY VIOLATION] Finding 1: `App.tsx` Broken JSX Syntax & Build Failure
- **What**: `frontend/src/App.tsx` contains mangled JSX, unclosed tags, and orphan code snippets resulting in **34 TypeScript syntax errors**.
- **Where**: `frontend/src/App.tsx` (lines 3051, 3172-3234, 4258, 4704, 4836, 5239)
- **Why**: When extracting inline sub-toolbar and sidebar controls into components, worker left mangled remnants in `App.tsx` (e.g. line 3172: `<I {!typesetInspectorCollapsed && (<SidebarInspector ... />)}/> ...`). Furthermore, running `npm run build` or `npx tsc --noEmit -p tsconfig.app.json` fails with exit code 1. Worker's claim of 0 TypeScript errors was false due to running `tsc` without referencing `tsconfig.app.json`.
- **Suggestion**: Clean up mangled inline JSX in `App.tsx`, remove dead code fragments, ensure all components render properly, and verify typecheck with `npx tsc --noEmit -p tsconfig.app.json` and `npm run build`.

### [Major] Finding 2: Requirement R2 Incomplete — OCR Engine Availability Filtering Missing
- **What**: OCR Engine options in `PipelineToolbar.tsx` and `SettingsModal.tsx` are static `<option>` tags without dynamic availability checking or disabling of unconfigured engines.
- **Where**: `frontend/src/components/PipelineToolbar.tsx` (lines 86-96) and `frontend/src/components/SettingsModal.tsx` (lines 204-214)
- **Why**: Requirement R2 explicitly requires: *"Automatically hide or clearly mark unusable engines when external dependencies or local API servers are absent, preventing confusing non-responsive UI actions."*
- **Suggestion**: Pass backend engine status / capability flags into `PipelineToolbar` and `SettingsModal` to disable or visually mark unusable choices.

### [Minor] Finding 3: Orphaned Inline Inspector Code Left in `App.tsx`
- **What**: Dead inline typography inspector controls (lines 3186–3230) were left inside `App.tsx` alongside the new `<SidebarInspector />` invocation.
- **Where**: `frontend/src/App.tsx` (lines 3172–3234)
- **Why**: Incomplete cleanup during refactoring.
- **Suggestion**: Remove all old inline template/character inspector JSX from `App.tsx`.

---

## 3. Verified Claims

| Claim / Command | Target / Scope | Result | Details |
|---|---|---|---|
| `pytest tests/` | Backend test suite | **PASS** | 196 tests passed (100% pass rate) |
| `npx vitest run` | Frontend tests | **PASS** | 16 test files passed, 113 tests passed |
| Sub-toolbar Modularization | `PipelineToolbar.tsx` | **PASS** | Extended props and controls extracted clean |
| Settings Modal Refactoring | `SettingsModal.tsx` | **PASS** | Categorized 7 tabs, store bindings clean |
| Sidebar Inspector Refactoring | `SidebarInspector.tsx` | **PASS** | Character panel & template chips clean |
| Root `npx tsc --noEmit` | `frontend/` root | **PASS (FALSE POSITIVE)** | Checks 0 files because root `tsconfig.json` uses `"files": []` |
| App `npx tsc --noEmit -p tsconfig.app.json` | `frontend/src/` | **FAIL** | 34 syntax errors in `App.tsx` |
| Production Build `npm run build` | `frontend/` | **FAIL** | `tsc -b` fails on `App.tsx` |

---

## 4. Attack Surface & Stress Test Results

- **Scenario 1**: Running production build (`npm run build`).  
  *Result*: **FAIL**. Compilation halts on line 3051 with `TS17008: JSX element 'main' has no corresponding closing tag` and 33 subsequent TS errors.
- **Scenario 2**: Selecting unconfigured local VLM OCR engine when local server is offline.  
  *Result*: **UNHANDLED**. Option remains selectable in UI without indication of offline status.

---

## 5. Summary Verdict

**Verdict**: **REQUEST_CHANGES**

Worker `worker_m1_1` must:
1. Fix the mangled JSX syntax and remove orphan code in `frontend/src/App.tsx`.
2. Ensure `npx tsc --noEmit -p tsconfig.app.json` and `npm run build` pass cleanly with 0 errors.
3. Implement dynamic availability / status disabling or visual marking for OCR Engines in `PipelineToolbar.tsx` and `SettingsModal.tsx` as per Requirement R2.
