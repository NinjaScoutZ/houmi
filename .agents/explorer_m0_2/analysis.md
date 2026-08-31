# Baseline Analysis Report: Backend Configuration & Schemas Audit

**Agent**: `explorer_m0_2`  
**Working Directory**: `e:\houmi\.agents\explorer_m0_2`  
**Date**: 2026-08-03  
**Baseline Test Status**: PASSED (196/196 tests passed in 48.06s)  

---

## 1. Executive Summary

This report presents a comprehensive investigation and audit of Houmi's Backend configuration files, database models, API schemas, service default settings, project serialization mechanisms, and backward compatibility rules.

### Key Discoveries:
1. **Test Suite Parity**: The backend `pytest` suite is fully functional and passing cleanly (`196 passed in 48.06s`).
2. **Configuration Redundancy**: Multiple backend services rely on chained fallback lookups (e.g., `key_a or key_b or default`) due to legacy key evolution over time. We identified 6 primary categories of redundant, duplicate, or aliased configuration keys across API payloads, DB settings, and service defaults.
3. **Parsing & Backward Compatibility**: Houmi maintains backward compatibility through runtime migration hooks (e.g., `migrate_project_translation_layout_policy`), legacy file path mirroring in `save_project_json`, deterministic hash validation in `TypesettingSpec`, and fallback parameter resolution in service modules.

---

## 2. Backend Architecture Overview & Investigated Files

The backend follows a FastAPI + SQLAlchemy architecture stored under `backend/app/`. The key files audited include:

| File Path | Primary Responsibility |
|---|---|
| `backend/app/config.py` | Global server config, model paths, execution provider maps |
| `backend/app/models/all_models.py` | SQLAlchemy ORM models (`Project`, `Page`, `TextBlock`, `TranslationMemory`) |
| `backend/app/schemas/all_schemas.py` | Top-level Pydantic schemas (`ProjectBase/Create/Response`, `TextBlockBase/Create/Update/Response`, `PageResponse`) |
| `backend/app/services/typesetting/schemas.py` | Canonical `TypesettingSpec` v2, `PaddingSpec`, `GradientSpec`, `LayoutRegionSpec` |
| `backend/app/services/typesetting/service.py` | Deterministic signature generation (`compute_block_signature`), layout fitting, Spec persistence |
| `backend/app/services/typesetting/fitting.py` | Token joining, font measurement, line height & tracking computation |
| `backend/app/services/project_serializer.py` | JSON serialization (`save_project_json`), portable annotation snapshots (`balloons.json`), legacy asset mirroring |
| `backend/app/services/serializer_hook.py` | SQLAlchemy `before_commit` / `after_commit` hooks for automatic project JSON sync |
| `backend/app/services/ocr.py` | Crop & OCR routing (PaddleOCR, DeepSeek OCR API, Gemini/agy CLI composite grid) |
| `backend/app/services/text_templates.py` | Built-in typography templates (`bubble`, `narration`, `emphasis`, `sfx`, `thought`, `system`) |
| `backend/app/services/inpainter.py` | Mask generation (adaptive/smart), LaMa / MAT / Telea inpainting engines |
| `backend/app/services/performance.py` | Performance profile resolution (`eco`, `balanced`, `performance`, `custom`) |
| `backend/app/routes/blocks.py` | CRUD for text blocks, geometry synchronization, inline semantic tag parsing |
| `backend/app/routes/projects.py` | Project creation (`_default_project_settings`), folder import, policy migration |
| `backend/app/routes/pipeline.py` | Detection, OCR, inpainting, rendering, training endpoints |
| `backend/app/routes/typesetting.py` | Recompute layout, preflight, style judge, feedback logging |

---

## 3. Configuration & Schema Key Audit

Across API payloads, DB `Project.settings` JSON, `TextBlock.extra_metadata` JSON, and service defaults, we identified the following redundant, duplicate, and legacy configuration keys:

### Category 1: OCR Engine & Backend Selection
* **Keys**: `ocr_engine`, `ocr_model`, `auto_ocr`
* **File Locations**: `backend/app/routes/blocks.py:154`, `backend/app/routes/pipeline.py`
* **Redundancy Analysis**:
  ```python
  ocr_backend = project_settings.get("ocr_engine") or project_settings.get("ocr_model")
  ```
  `ocr_model` is a legacy alias for `ocr_engine`. Both exist in DB project settings.
* **Gemini/AI Model Parsing**: `services/ocr.py` accepts string formats like `gemini:flash`, `gemini:flash_lite`, `agy`, `ai`.

### Category 2: Inpainting & Clean Strategy Options
* **Keys**: `inpaint_engine`, `active_inpaint_engine`, `default_image_inpaint_method`, `cleanup_pipeline_profile`, `cleanup_mask_strategy`, `force_lama_inpaint`
* **File Locations**: `backend/app/services/inpainter.py:461-463`, `backend/app/routes/pipeline.py:1551-1553`, `backend/app/routes/projects.py:26-30`
* **Redundancy Analysis**:
  ```python
  engine = (
      settings.get("inpaint_engine")
      or settings.get("active_inpaint_engine")
      or settings.get("default_image_inpaint_method", "LamaInpaint")
  )
  ```
  Three separate keys represent the inpainting engine!
  Furthermore:
  - `cleanup_pipeline_profile` ("smart_lama") and `cleanup_mask_strategy` ("smart" vs "legacy_adaptive") both configure cleaning strategy.
  - `force_lama_inpaint` (boolean default `True`) is redundant when `inpaint_engine` is `"LamaInpaint"`.

### Category 3: GPU & Execution Provider Selection
* **Keys**: `gpu_execution_provider`, `execution_provider`
* **File Locations**: `backend/app/routes/pipeline.py:92`, `backend/app/services/inpainter.py:1215`
* **Redundancy Analysis**:
  ```python
  gpu_ep = project_settings.get("gpu_execution_provider") or project_settings.get("execution_provider")
  ```
  `gpu_execution_provider` and `execution_provider` are duplicate keys stored in settings to specify ONNX Runtime providers (`CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`).

### Category 4: Lexicon & Dictionary Settings
* **Keys**: `project_dictionary`, `thai_dictionary`
* **File Locations**: `backend/app/services/typesetting/service.py:152`
* **Redundancy Analysis**:
  ```python
  proj_dict = project_settings.get("project_dictionary") or project_settings.get("thai_dictionary") or []
  ```
  `thai_dictionary` is a legacy Thai-specific key that was generalized to `project_dictionary` for proper-name tokenization.

### Category 5: TypesettingSpec Canonical Aliases & Parity
* **Keys**:
  - `layout_engine_version` vs `layout_version` (`services/typesetting/schemas.py:65-66`)
  - `resolved_postscript_name` vs `font_postscript_name` (`services/typesetting/schemas.py:88`)
  - `horizontal_align` vs `text_align` (`services/typesetting/schemas.py:111`)
  - `letter_spacing` vs `tracking` (`services/text_templates.py:223-224`, `services/typesetting/service.py:95`)
* **Redundancy Analysis**: `TypesettingSpec` explicitly mirrors `layout_version` = `layout_engine_version`, `font_postscript_name` = `resolved_postscript_name`, and `text_align` = `horizontal_align` to ensure backward compatibility with older frontend exporters and PSD renderers.

### Category 6: Font Sizing & Typography Override State
* **Keys**:
  - `font_size` (DB Column on `TextBlock`)
  - `manual_font_size`, `font_size_mode` ("auto" | "manual"), `min_font_size`, `max_font_size`, `preferred_font_size` (stored in `TextBlock.extra_metadata`)
  - `min_font_size`, `max_font_size`, `auto_font_resize` (stored in `Project.settings`)
* **Interaction Logic**:
  - `_sync_manual_font_size(block)` in `routes/typesetting.py` ensures that if `manual_font_size` exists in `extra_metadata`, `block.font_size` is locked to that value.
  - `_apply_block_update` in `routes/blocks.py` sets `font_size_mode = "manual"` whenever an API call updates `font_size` without specifying `font_size_mode = "auto"`.

---

## 4. Stored Project Files Parsing & Backward Compatibility

Houmi maintains compatibility with projects created across different versions through several architectural mechanisms:

### A. Project Serialization Format (`project.json`)
* **Trigger**: SQLAlchemy `after_commit` event in `services/serializer_hook.py` calls `save_project_json(project_id)`.
* **Locations**:
  1. Main DB storage: `data/projects/{project_id}/project.json`
  2. Workspace mirror: `{workspace_dir}/houmi_project.json`
  3. Portable training snapshot: `data/projects/{project_id}/training/balloons.json`
* **Data Structure**:
  ```json
  {
    "id": "uuid",
    "name": "Project Name",
    "source_lang": "ja",
    "target_lang": "th",
    "settings": { ... },
    "pages": [
      {
        "id": "page_uuid",
        "page_number": 1,
        "width": 1000,
        "height": 1500,
        "source_image_path": "...",
        "text_blocks": [
          {
            "id": "block_uuid",
            "x": 100.0, "y": 150.0, "width": 200.0, "height": 80.0,
            "source_text": "...",
            "translation": "...",
            "font_family": "NotoSansThai",
            "font_size": 24.0,
            "extra_metadata": {
              "typesetting_spec": { ... }
            }
          }
        ]
      }
    ]
  }
  ```

### B. Legacy Asset & Directory Mirroring
In `services/project_serializer.py`, legacy nested page paths (`clean/inpainted.png`, `rendered/rendered.png`, `masks/*.png`) are mirrored to flat layout structures:
- `inpainted_asset_path(page)`
- `inpaint_preview_asset_path(page)`
- `rendered_asset_path(page)`
- `mask_asset_path(page, name)`

### C. Automated Migration Rules
When a project is fetched via `GET /projects/{project_id}`, `migrate_project_translation_layout_policy(db_project)` runs:
- Increments `translation_layout_policy_version` to `TRANSLATION_LAYOUT_POLICY_VERSION` (version 1).
- Converts legacy detection-box locked text coordinates into safe balloon interior layout regions.

### D. Spec Invalidation & Recomputation
`validate_typesetting_spec(block, spec)` in `services/typesetting/service.py`:
- Calculates a SHA-256 `source_signature` of block parameters (text, geometry, font, tracking, line height, dictionary tokens, schema versions).
- If `spec.source_signature != expected_sig` or `spec.schema_version != TYPESETTING_SCHEMA_VERSION`, the cached spec is invalidated and recomputed on demand.

### E. Backward Compatibility Strategy for Cleanup
When consolidating setting schemas:
1. **Read Path**: Continue supporting legacy keys as fallback reads (`new_key = settings.get("canonical_key") or settings.get("legacy_key") or default`).
2. **Write Path**: Always write to the single canonical key.
3. **Database Migration / Normalization**: On project load or update, migrate legacy keys into canonical keys while preserving extra custom metadata.

---

## 5. Baseline Test Status Verification

The entire backend test suite was executed using Python 3.11 in the project virtual environment:

**Command**:
```powershell
e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/
```

**Results**:
- **Total Test Files**: 33
- **Total Test Cases**: 196
- **Passed**: 196
- **Failed**: 0
- **Errors**: 0
- **Duration**: 48.06s

### Summary of Passing Test Modules:
- `test_autofit_constraints.py` (2 passed)
- `test_block_geometry_contract.py` (1 passed)
- `test_browser_render.py` (5 passed)
- `test_detector_postprocessing.py` (3 passed)
- `test_diagnostics.py` (2 passed)
- `test_execution_provider.py` (4 passed)
- `test_fast_preview.py` (1 passed)
- `test_font_registry.py` (6 passed)
- `test_gemini_ocr.py` (5 passed)
- `test_image_export.py` (2 passed)
- `test_inpaint_preview.py` (6 passed)
- `test_inpaint_preview_scope.py` (3 passed)
- `test_inpainter.py` (15 passed)
- `test_layout_region.py` (6 passed)
- `test_mask_editor_contract.py` (2 passed)
- `test_memory_cache.py` (3 passed)
- `test_performance.py` (2 passed)
- `test_photoshop_gradient.py` (2 passed)
- `test_pipeline_text_evidence.py` (4 passed)
- `test_production_smoke.py` (1 passed)
- `test_project_paths.py` (1 passed)
- `test_psd_roundtrip.py` (1 passed)
- `test_stroke_and_dictionary.py` (12 passed)
- `test_style_judge.py` (14 passed)
- `test_style_judge_pipeline.py` (1 passed)
- `test_text_mask.py` (6 passed)
- `test_text_templates.py` (8 passed)
- `test_tile_inpainting.py` (3 passed)
- `test_txt_exchange.py` (54 passed)
- `test_typesetting.py` (21 passed)

---

## 6. Recommendations for Refactoring & Consolidation

1. **OCR Engine Key Consolidation**: Standardize `Project.settings` on `ocr_engine`. Maintain `ocr_model` as a read-only fallback in getter functions.
2. **Inpaint Engine Key Consolidation**: Standardize `Project.settings` on `inpaint_engine`. Deprecate `active_inpaint_engine` and `default_image_inpaint_method` by aliasing them to `inpaint_engine`.
3. **Execution Provider Key Consolidation**: Standardize `Project.settings` on `execution_provider`. Deprecate `gpu_execution_provider`.
4. **Dictionary Key Consolidation**: Standardize `Project.settings` on `project_dictionary`. Deprecate `thai_dictionary`.
5. **Typesetting Schema Cleanliness**: Retain output field aliases in `TypesettingSpec` for frontend/export contract compatibility, but document them explicitly as backward-compatibility aliases.
