# Houmi OCR Engines & Pipeline Organization Specification Analysis

**Author**: `spec_miner_m0_1`  
**Date**: 2026-08-03  
**Target Project**: Houmi (Offline Desktop Manga Translation Studio)  
**Assigned Mission**: Investigate and extract specifications for OCR Engines & Pipeline organization.

---

## 1. Executive Summary & Specification Scope

The Houmi platform utilizes an OCR (Optical Character Recognition) pipeline to transcribe text from detected manga speech balloons and text regions. This analysis provides an exhaustive specification of all OCR engines present in the codebase, traces their end-to-end integration across frontend UI controls and backend execution pathways, evaluates current diagnostic capabilities, and details a unified specification for dynamically detecting, categorizing, and enabling/disabling OCR engines based on runtime environment readiness.

---

## 2. Complete Identification & Categorization of OCR Engines

Across the Houmi codebase, six distinct OCR engine identifiers exist across UI dropdowns, backend services, and external sub-processes. They fall into three primary architecture categories: **AI Cloud / AI CLI**, **Local Offline VLM API (Vision Language Model)**, **Local Offline Traditional Engine**, plus **Unsupported Legacy Entries**.

### Summary Matrix of OCR Engines

| Engine Name | Identifier / Key | Category | Runtime / Protocol | File Implementation | Dependencies & Requirements | Current Codebase Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gemini 3.6 Flash (AGY AI)** | `gemini`<br>`gemini:flash`<br>`gemini:flash_lite` | AI Cloud / AI CLI | Local CLI invocation via `subprocess.run` (`agy` or `gemini` executable) | `backend/app/services/ocr.py` | Installed `agy` or `gemini` CLI tool in PATH, Google AI API credentials | **Fully Implemented** (Includes 12-block Composite Grid Batch OCR) |
| **GLM-OCR (VLM)** | `glm`<br>`glm-ocr` | Local Offline VLM API | Subprocess HTTP server (`127.0.0.1:2322/ocr`) | `backend/ocr_server/server.py`<br>`GLMBackend` | `zai-org/GLM-OCR` model weights, PyTorch + CUDA/CPU, sub-process running | **Fully Implemented** (Default fallback for local VLM server) |
| **DeepSeek-OCR (VLM)** | `deepseek`<br>`deepseek-ocr` | Local Offline VLM API | Subprocess HTTP server (`127.0.0.1:2322/ocr`) | `backend/ocr_server/server.py`<br>`DeepSeekBackend` | `deepseek-ai/DeepSeek-OCR-2` model weights, PyTorch + CUDA, sub-process running | **Fully Implemented** (Primary local VLM model) |
| **PaddleOCR (Korean)** | `paddleocr`<br>`paddle_ocr` | Local Offline Engine | Direct Python import or Subprocess HTTP (`127.0.0.1:2322/ocr?backend=paddleocr`) | `backend/app/services/ocr.py`<br>`backend/ocr_server/server.py` | `paddleocr` Python package, `paddlepaddle` framework, Korean model weights | **Fully Implemented** (Korean-focused offline deep learning OCR) |
| **Manga-OCR** | `manga_ocr` | Local Offline Engine | *None (UI Placeholder only)* | `frontend/src/components/SettingsModal.tsx` | `manga-ocr` Python package (missing from backend) | **Unimplemented UI Stray** (Appears in Settings Modal dropdown only) |
| **RapidOCR** | `rapid_ocr` | Local Offline Engine | *None (UI Placeholder only)* | `frontend/src/components/SettingsModal.tsx` | `rapidocr_onnxruntime` Python package (missing from backend) | **Unimplemented UI Stray** (Appears in Settings Modal dropdown only) |

---

### Detailed Engine Breakdown

#### 1. Gemini 3.6 Flash / AGY AI (`gemini`)
- **Backend Location**: `backend/app/services/ocr.py` (`_run_gemini_command`, `_run_gemini_cli_ocr`, `batch_grid_crop_and_ocr_gemini`)
- **Execution Mechanism**: Invokes the local CLI tool `agy` (or `gemini`) via standard output piping with `--print --model flash` flags.
- **Batch Grid Optimization**: When running full-page or multi-block OCR with Gemini, Houmi composites up to 12 cropped speech balloons into a single labeled composite grid image (`HOUMI_BOX:BOX_001_...`), making a single CLI call. This reduces API latency and request count by ~10x while utilizing stable box ID matching.
- **Hardware Requirements**: Minimal local CPU/GPU (offloaded to cloud API via CLI).
- **Prerequisites**: Installed `agy` or `gemini` executable in system PATH; active network connection & API key configuration.

#### 2. GLM-OCR (`glm`)
- **Backend Location**: `backend/ocr_server/server.py` (`GLMBackend`)
- **Execution Mechanism**: Managed background HTTP server running on `http://127.0.0.1:2322/ocr` launched by `backend/app/ocr_manager.py`. Uses `AutoModelForImageTextToText` (`zai-org/GLM-OCR`).
- **Hardware Requirements**: Recommended GPU (CUDA, bfloat16/4-bit quantization). Supports CPU fallback.
- **Prerequisites**: `ocr_server` subprocess active, PyTorch, Transformers, model checkpoint downloaded.

#### 3. DeepSeek-OCR (`deepseek`)
- **Backend Location**: `backend/ocr_server/server.py` (`DeepSeekBackend`)
- **Execution Mechanism**: Managed background HTTP server (`http://127.0.0.1:2322/ocr`). Uses `AutoModel` (`deepseek-ai/DeepSeek-OCR-2`).
- **Auto Fallback**: If DeepSeek encounters CUDA MoE memory exceptions on Windows, `server.py` automatically falls back to `GLMBackend` gracefully without failing the user request.
- **Hardware Requirements**: NVIDIA CUDA GPU (high VRAM requirement).
- **Prerequisites**: `ocr_server` subprocess active, CUDA environment.

#### 4. PaddleOCR (`paddleocr` / `paddle_ocr`)
- **Backend Location**: `backend/app/services/ocr.py` (`_get_paddle_ocr`) and `backend/ocr_server/server.py` (`PaddleOCRBackend`)
- **Execution Mechanism**: Direct in-process execution in backend via `paddleocr.PaddleOCR(lang='korean')` or HTTP request to `ocr_server`.
- **Hardware Requirements**: Light-to-moderate CPU/GPU usage.
- **Prerequisites**: `paddlepaddle` and `paddleocr` installed in backend virtual environment.

#### 5. Manga-OCR (`manga_ocr`) & RapidOCR (`rapid_ocr`)
- **Location**: `frontend/src/components/SettingsModal.tsx`
- **Codebase Reality**: Found ONLY in `SettingsModal.tsx` as static `<option>` tags. Zero underlying backend route, service handler, or model loading code exists for `manga_ocr` or `rapid_ocr` in `backend/app/services/ocr.py` or `backend/ocr_server/server.py`.

---

## 3. Implementation Tracing across Frontend & Backend

### Frontend UI Tracing

1. **Sub-toolbar OCR Selector (`frontend/src/App.tsx`)**:
   - **File**: `frontend/src/App.tsx` (Lines 2856-2865)
   - **State**: `const [ocrEngine, setOcrEngine] = useState('glm');` (Line 379)
   - **Render condition**: Rendered only when `workspaceMode === 'ocr'` (Sub-toolbar).
   - **Options Present**:
     - `gemini`: Gemini 3.6 Flash (AGY AI)
     - `glm`: GLM-OCR (VLM)
     - `deepseek`: DeepSeek-OCR (VLM)
     - `paddleocr`: PaddleOCR (Korean)

2. **Global Settings Modal (`frontend/src/components/SettingsModal.tsx`)**:
   - **File**: `frontend/src/components/SettingsModal.tsx` (Lines 67-79)
   - **State**: Binds to `activeProject.settings.ocr_model` / `ocr_engine`.
   - **Options Present**:
     - `manga_ocr`: manga_ocr (Manga-OCR) *(Stray option)*
     - `rapid_ocr`: rapid_ocr (RapidOCR) *(Stray option)*
     - `paddle_ocr`: paddle_ocr (PaddleOCR)
     - `gemini`: gemini (Gemini AI)
   - **Divergence Issue**: The dropdown in `SettingsModal.tsx` lists completely different options than `App.tsx` sub-toolbar! `SettingsModal` misses `glm` and `deepseek`, while containing non-functional `manga_ocr` and `rapid_ocr`.

3. **Pipeline Action Trigger (`frontend/src/components/PipelineToolbar.tsx` & `App.tsx`)**:
   - **File**: `frontend/src/components/PipelineToolbar.tsx` (Lines 42-50)
   - **Action**: Triggers `onRunStep('ocr')`.
   - **Execution in `App.tsx`**: `runPipelineStep('ocr')` (Lines 1766-1777) calls backend API:
     - GET `/api/pipeline/ocr?page_id=${activePage.id}&force=true&backend=${ocrEngine}`
     - Or POST `/api/pipeline/auto/background?page_id=${activePage.id}&project_id=${activeProject.id}&backend=${ocrEngine}`

4. **Diagnostics Badge (`frontend/src/components/PipelineToolbar.tsx`)**:
   - **File**: `frontend/src/components/PipelineToolbar.tsx` (Lines 107-133)
   - **Backend Status Props**: Displays `online` (green pulse), `degraded` (amber pulse), or `offline` (red). Triggers `onOpenDiagnostics` modal.

---

### Backend Pipeline & Server Tracing

1. **Pipeline Route (`backend/app/routes/pipeline.py`)**:
   - **Endpoint**: `@router.post("/pipeline/ocr")` / `run_ocr(page_id, backend, force, target_ids, db)`
   - **Behavior**: Retrieves `ocr_targets` from `page.text_blocks`. Passes `backend` string to `crop_and_ocr_blocks_parallel(source_image_path, ocr_targets, backend=backend, source_lang=source_lang)`.

2. **OCR Service Layer (`backend/app/services/ocr.py`)**:
   - **Parallel / Batch Dispatch**: `crop_and_ocr_blocks_parallel()`:
     - If `backend` contains `"gemini"`, `"ai"`, or `"agy"`: Delegates to `batch_grid_crop_and_ocr_gemini()`.
     - Else: Runs `ThreadPoolExecutor` calling `crop_and_ocr_block()`.
   - **Block OCR Dispatch**: `crop_and_ocr_block()`:
     - `backend == "gemini"` -> `_run_gemini_cli_ocr()`
     - `backend == "paddleocr"` -> `_get_paddle_ocr()`
     - Otherwise -> POST to `OCR_API_URL` (`http://127.0.0.1:2322/ocr?backend={backend}`).

3. **Subprocess Management (`backend/app/ocr_manager.py` & `backend/app/main.py`)**:
   - **Lifecyle**: On backend FastAPI startup (`main.py` line 239), `ocr_manager.start_server()` spawns `backend/ocr_server/server.py` on port 2322 using its virtual environment (`backend/ocr_server/venv`).
   - **Health Maintenance Thread**: Daemon thread in `ocr_manager.maintain_server()` continuously pings `http://127.0.0.1:2322/health` every 10s and restarts the process if dead or unresponsive.

4. **OCR Subprocess Server (`backend/ocr_server/server.py`)**:
   - Bottle HTTP server listening on port 2322.
   - Endpoints:
     - `POST /ocr` or `POST /ocr_direct`: Receives image upload & `backend` query param (`deepseek`, `glm`, `paddleocr`).
     - `GET /health`: Returns `{ "status": "ok", "backend": "glm", "model": "...", "device": "cuda", "model_loaded": true, "last_error": null }`.

5. **Diagnostics Endpoint (`backend/app/routes/diagnostics.py`)**:
   - **Endpoint**: `GET /diagnostics/health`
   - **OCR Check**: Evaluates `ocr_manager.check_health()`. Reports `"ocr": { "status": "ok"|"error", "message": "..." }`.

---

## 4. Dynamic Unusable / Unconfigured Engine Detection & UI Disabling Specification

### Current Architectural Deficiencies
1. **Hardcoded UI Dropdowns**: Dropdown items in both `App.tsx` and `SettingsModal.tsx` are hardcoded without inspecting actual backend capabilities or CLI availability.
2. **Divergent Dropdown Definitions**: `App.tsx` sub-toolbar and `SettingsModal.tsx` modal have completely un-synchronized `<option>` lists.
3. **Silent Failure / Non-Responsive UX**: If a user selects `gemini` without `agy`/`gemini` installed in PATH, or selects `deepseek` when `ocr_server` fails to initialize, requests fail silently or log errors in background without disabling or warning the user in UI.

---

### Specification for Dynamic Engine Discovery & Disabling

To fulfill Requirement R2 ("Automatically hide or clearly mark unusable engines when external dependencies or local API servers are absent, preventing confusing non-responsive UI actions"), the system must implement a dynamic health-and-capability discovery contract.

#### 1. Backend Engine Capability API Endpoint Specification

**Endpoint**: `GET /api/pipeline/ocr/engines` (or integrated into `GET /api/diagnostics/health`)

**Response Schema**:
```json
{
  "active_engine": "glm",
  "engines": [
    {
      "id": "gemini",
      "name": "Gemini 3.6 Flash (AGY AI)",
      "category": "cloud_ai",
      "status": "available",
      "available": true,
      "reason": null,
      "details": {
        "cli_found": true,
        "cli_binary": "agy"
      }
    },
    {
      "id": "glm",
      "name": "GLM-OCR (VLM)",
      "category": "local_vlm",
      "status": "available",
      "available": true,
      "reason": null,
      "details": {
        "server_alive": true,
        "device": "cuda",
        "model_loaded": true
      }
    },
    {
      "id": "deepseek",
      "name": "DeepSeek-OCR (VLM)",
      "category": "local_vlm",
      "status": "disabled",
      "available": false,
      "reason": "Insufficient CUDA VRAM for DeepSeek MoE",
      "details": {
        "server_alive": true,
        "device": "cuda"
      }
    },
    {
      "id": "paddleocr",
      "name": "PaddleOCR (Korean)",
      "category": "local_offline",
      "status": "available",
      "available": true,
      "reason": null,
      "details": {
        "package_installed": true
      }
    }
  ]
}
```

#### 2. Health & Detection Logic Rules

- **Gemini (`gemini`) Detection**:
  - Backend checks `shutil.which("agy") or shutil.which("gemini")`.
  - If neither binary is present in system PATH, `available = false`, `reason = "Neither 'agy' nor 'gemini' CLI found in system PATH"`.

- **Local VLM Server (`glm`, `deepseek`) Detection**:
  - Backend queries `ocr_manager.check_health()` and `http://127.0.0.1:2322/health`.
  - If `ocr_server` subprocess is offline or crashing, `available = false`, `reason = "Local VLM server (port 2322) unavailable"`.
  - If `ocr_server` is in fallback mode due to CUDA illegal memory access, `deepseek` marked `disabled` with explanatory reason while `glm` remains `available`.

- **PaddleOCR (`paddleocr`) Detection**:
  - Backend attempts `import paddleocr`. If `ImportError`, `available = false`, `reason = "paddleocr package not installed"`.

- **Stray / Unsupported Engines (`manga_ocr`, `rapid_ocr`)**:
  - Removed completely from UI dropdown schemas.

#### 3. Frontend Unified Dropdown Component Specification

Replace duplicate dropdown implementations in `App.tsx` and `SettingsModal.tsx` with a single unified component: `<OcrEngineSelector />`.

**UI Behavior Requirements**:
1. Categorized dropdown headers (Optgroups):
   - ☁️ **Cloud AI / CLI**: Gemini 3.6 Flash
   - ⚡ **Local Offline VLM**: GLM-OCR, DeepSeek-OCR
   - 📦 **Local Offline Engine**: PaddleOCR
2. **Disabled State Representation**:
   - If an engine has `available === false`, render the option as `disabled`.
   - Append `(Unavailable - [Reason])` to option label.
   - Display a warning tooltip explaining missing prerequisite (e.g. "Install agy CLI to enable Gemini OCR").
3. **Auto-Fallback Safeguard**:
   - If the project's saved `ocr_engine` becomes unavailable, automatically select the first available engine (e.g. `glm`) and show a soft warning toast.

---

## 5. Affected Files & Relevant Test Suite Inventory

### Backend Affected Files

| File Path | Role in OCR Pipeline | Key Functions / Components |
| :--- | :--- | :--- |
| `backend/app/services/ocr.py` | Core OCR service implementation | `crop_and_ocr_block()`, `batch_grid_crop_and_ocr_gemini()`, `crop_and_ocr_blocks_parallel()`, `_run_gemini_cli_ocr()`, `_get_paddle_ocr()` |
| `backend/ocr_server/server.py` | Subprocess VLM server | `GLMBackend`, `DeepSeekBackend`, `PaddleOCRBackend`, `OCRService`, `/ocr`, `/health` |
| `backend/app/ocr_manager.py` | Subprocess lifecycle manager | `OCRManager.start_server()`, `stop_server()`, `check_health()`, `maintain_server()` |
| `backend/app/routes/pipeline.py` | Pipeline execution API route | `@router.post("/pipeline/ocr")`, `run_ocr()`, `clean_ocr_text()`, `_process_ocr_evidence_results()` |
| `backend/app/routes/diagnostics.py` | Health inspection API route | `@router.get("/diagnostics/health")` |
| `backend/app/routes/blocks.py` | Text block API route | `auto_ocr` execution in block creation/updates |
| `backend/app/config.py` | Subprocess server configuration | `OCR_PORT`, `OCR_HOST`, `OCR_API_URL`, `OCR_SERVER_DIR` |
| `backend/app/main.py` | Application lifecycle | Subprocess startup/shutdown hooks |

### Frontend Affected Files

| File Path | Role in OCR Pipeline | Key Components / Logic |
| :--- | :--- | :--- |
| `frontend/src/App.tsx` | Main application view & sub-toolbar | `ocrEngine` state, Sub-toolbar OCR dropdown (lines 2856-2865), `runPipelineStep('ocr')` (lines 1766-1777) |
| `frontend/src/components/SettingsModal.tsx` | Project global settings modal | Active OCR Model dropdown (lines 68-79), updates `ocr_model` / `ocr_engine` |
| `frontend/src/components/PipelineToolbar.tsx` | Pipeline execution & status bar | OCR step button (lines 42-50), backend status indicator badge (lines 107-133) |
| `frontend/src/stores/projectStore.ts` | Project state management | Project settings store holding `ocr_model` / `ocr_engine` |

### Test Files (Parity & Regression Coverage)

| Test File Path | Test Suite Framework | Target Area & Specifications Tested | Status |
| :--- | :--- | :--- | :--- |
| `backend/tests/test_gemini_ocr.py` | `pytest` | Gemini CLI command execution, grid response mapping by stable box ID, prompt language formatting | ✅ Passing |
| `backend/tests/test_pipeline_text_evidence.py` | `pytest` | Pipeline OCR step execution, text evidence classification, candidate block promotion/pruning | ✅ Passing |
| `backend/tests/test_diagnostics.py` | `pytest` | Diagnostics health check route (`/diagnostics/health`) and OCR server status reporting | ✅ Passing |
| `frontend/src/tests/settingsModal.test.ts` | `vitest` | Settings modal OCR model selection store integration (`ocr_model`, `ocr_engine`) | ✅ Passing |
| `frontend/src/tests/diagnosticsToolbar.test.ts` | `vitest` | PipelineToolbar status badge props and diagnostic modal interaction | ✅ Passing |

---

## 6. Features Discovered & Edge Cases

### Features Discovered Table

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | AI Cloud / CLI | Composite Grid Batch OCR | Packs up to 12 text blocks into a single labeled composite grid image to perform OCR in 1 CLI call. | Image path, array of `TextBlock` instances, `source_lang` | Array of `(TextBlock, ocr_text, success)` tuples | Falls back to individual block OCR if batch CLI fails | `backend/app/services/ocr.py` |
| 2 | Local VLM | Windows MoE Auto-Fallback | Automatically switches server backend from DeepSeek to GLM if CUDA illegal memory access occurs. | Image upload to `/ocr` endpoint | Transcribed text lines + active backend metadata | Switches `ocr_service.backend_name` to `"glm"` and retries inference | `backend/ocr_server/server.py` |
| 3 | Local Offline | In-Process PaddleOCR | Initializes local PaddleOCR (Korean) model on GPU/CPU for direct in-memory block OCR. | Image crop path | Transcribed text string | Returns `("", False)` on import/execution failure | `backend/app/services/ocr.py` |
| 4 | Health & Diag | OCR Subprocess Keep-Alive | Daemon thread pings port 2322 health endpoint and force-restarts process if unresponsive. | Port `2322` TCP socket & HTTP `/health` | Subprocess status boolean | Restarts Python process `server.py` inside `ocr_server/venv` | `backend/app/ocr_manager.py` |
| 5 | UI Settings | Sub-toolbar vs Modal Engine Dropdowns | Sub-toolbar (`App.tsx`) and Settings Modal (`SettingsModal.tsx`) provide separate OCR engine dropdown controls. | User selection event | Local component state / project settings update | Dropdown options diverge; stray unimplemented options (`manga_ocr`, `rapid_ocr`) exist in modal | Code analysis of `App.tsx` & `SettingsModal.tsx` |

### Edge Cases Table

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Composite Grid Batch OCR | Gemini Vision model alters box ID prefix (e.g. returns `HOUMI_BOX_BOX_001_...` instead of `HOUMI_BOX:BOX_001_...`) | `_parse_gemini_grid_response` uses stable suffix matching to correctly attribute text to `TextBlock` without requiring secondary fallback OCR. |
| 2 | DeepSeek MoE CUDA Execution | Windows CUDA illegal memory access exception during inference | `server.py` catches `exc`, logs warning, switches backend to `GLMBackend`, synchronizes CUDA memory, and completes OCR using GLM. |
| 3 | Missing `agy` / `gemini` CLI | User selects `gemini` engine when CLI tool is not installed in PATH | `_run_gemini_command` logs error "Neither 'agy' nor 'gemini' CLI tool found in PATH" and returns `("", False)`. |
| 4 | Settings Modal Model Selection | User selects `manga_ocr` or `rapid_ocr` in Global Settings modal | Project settings update to `ocr_model = "manga_ocr"`, but pipeline execution defaults to local `ocr_server` API on port 2322 without error warning. |
| 5 | Crop Boundary Bounds | Text block coordinates extend beyond image width/height | `crop_and_ocr_block` clamps crop boundaries `x0, y0, x1, y1` to image dimensions `[0, w_img]` and `[0, h_img]`. |
