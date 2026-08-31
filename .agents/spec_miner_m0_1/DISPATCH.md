## 2026-08-03T15:52:27Z
You are spec_miner_m0_1 for Houmi.
Working directory: e:\houmi\.agents\spec_miner_m0_1
Original request path: e:\houmi\.agents\ORIGINAL_REQUEST.md

Task:
Read e:\houmi\.agents\ORIGINAL_REQUEST.md.
Investigate and extract specifications for OCR Engines & Pipeline organization:
1. Identify all supported OCR engines in the codebase (Local offline engines like PaddleOCR/MangaOCR, AI Cloud like Baidu/Google/OpenAI, Local VLM API like Ollama/vLLM).
2. Trace where OCR engine dropdowns, configuration forms, API health checks, and engine selection logic are implemented in both frontend and backend.
3. Determine how unusable or unconfigured engines (missing local models, unconfigured API keys, offline local VLM servers) can be detected and hidden/disabled dynamically in the UI to prevent non-responsive user actions.
4. Document all affected frontend/backend files and relevant test files.

Write your complete spec analysis report to e:\houmi\.agents\spec_miner_m0_1\analysis.md and create a handoff.md. Send a message when complete.
