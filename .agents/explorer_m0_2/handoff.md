# Handoff Report — Backend Configuration & Schemas Audit (`explorer_m0_2`)

## 1. Observation

- **Pytest Baseline**: Executed `e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/` in `e:\houmi\backend`. Output: `196 passed, 8 warnings in 76.66s`. Zero test failures.
- **OCR Settings Redundancy**:
  - `backend/app/routes/blocks.py:154`: `ocr_backend = project_settings.get("ocr_engine") or project_settings.get("ocr_model")`
  - `backend/app/services/ocr.py`: Accepts Gemini/AI engine model strings (`gemini:flash`, `gemini:flash_lite`, `agy`, `ai`).
- **Inpainting & Cleanup Settings Redundancy**:
  - `backend/app/services/inpainter.py:461-463` and `backend/app/routes/pipeline.py:1551-1553`:
    ```python
    engine = settings.get("inpaint_engine") or settings.get("active_inpaint_engine") or settings.get("default_image_inpaint_method", "LamaInpaint")
    ```
  - `backend/app/routes/projects.py:26-30`: Specifies default project settings with `cleanup_pipeline_profile: "smart_lama"`, `cleanup_mask_strategy: "smart"`, `force_lama_inpaint: True`, `default_image_inpaint_method: "LamaInpaint"`.
- **GPU Execution Provider Redundancy**:
  - `backend/app/routes/pipeline.py:92` and `backend/app/services/inpainter.py:1215`:
    ```python
    gpu_ep = project_settings.get("gpu_execution_provider") or project_settings.get("execution_provider")
    ```
- **Dictionary Setting Redundancy**:
  - `backend/app/services/typesetting/service.py:152`:
    ```python
    proj_dict = project_settings.get("project_dictionary") or project_settings.get("thai_dictionary") or []
    ```
- **TypesettingSpec Schema Aliases**:
  - `backend/app/services/typesetting/schemas.py:65-66`: `layout_engine_version` is canonical, `layout_version` is a legacy alias.
  - `backend/app/services/typesetting/schemas.py:88`: `resolved_postscript_name` is canonical, `font_postscript_name` is an export parity alias.
  - `backend/app/services/typesetting/schemas.py:111`: `horizontal_align` is canonical, `text_align` is an alias.
- **Pydantic & FastAPI Warnings**:
  - `backend/app/schemas/all_schemas.py`: Uses deprecated `class Config` instead of Pydantic v2 `model_config = ConfigDict(from_attributes=True)`.
  - `backend/app/main.py`: Uses deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`.

## 2. Logic Chain

1. **Baseline Integrity**:
   - Direct execution of the full backend pytest suite confirmed 100% test passage (196/196 tests).
   - This provides a solid baseline for any subsequent refactoring or setting cleanup tasks.
2. **Identification of Redundancies**:
   - Traced all setting reads across routes and services. In multiple places, developers added new configuration key names without deprecating or migrating old ones, resulting in chained OR fallbacks (`key_1 or key_2 or key_3`).
   - Standardizing on canonical keys (`ocr_engine`, `inpaint_engine`, `execution_provider`, `project_dictionary`) and wrapping accessors in a unified helper will eliminate payload clutter while maintaining full backward compatibility.
3. **Backward Compatibility & Parsing Mechanics**:
   - `project.json` stores arbitrary dict settings per project and `extra_metadata` per text block.
   - `migrate_project_translation_layout_policy` handles runtime version migration of stored project files on fetch.
   - Deterministic SHA-256 signature verification in `compute_block_signature` ensures cached typesetting specs automatically invalidate when block options or dictionaries change.

## 3. Caveats

- **Frontend Payload Alignment**: While backend services handle fallback reading gracefully, frontend components (Sub-toolbar, Canvas controls, Global Settings modal) must be audited to ensure they send and read canonical key names to prevent setting mismatch.
- **Stored SQLite Databases**: Production databases may contain stored projects with legacy keys (`ocr_model`, `thai_dictionary`, `gpu_execution_provider`). Implementers should ensure fallback getters remain in place or perform transparent key renaming during project load.

## 4. Conclusion

The backend configuration and schema audit is complete.
1. The backend test suite is 100% passing (196/196 tests).
2. Four major key duplication clusters (`ocr_engine`/`ocr_model`, `inpaint_engine`/`active_inpaint_engine`/`default_image_inpaint_method`, `gpu_execution_provider`/`execution_provider`, `project_dictionary`/`thai_dictionary`) have been documented with exact locations and fallback patterns.
3. Complete baseline analysis has been recorded in `analysis.md`.

## 5. Verification Method

To verify these findings independently:
1. Run backend pytest suite:
   ```powershell
   e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/
   ```
   (Verify 196 passed).
2. Inspect `analysis.md` for line numbers and exact code references.
