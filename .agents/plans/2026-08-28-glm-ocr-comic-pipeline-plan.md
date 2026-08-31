# GLM-OCR Comic Pipeline Architecture & Integration Plan

**MODE:** GODKILLER (Self-Pilot)  
**GOAL:** Isolate and enhance GLM-OCR for Manga/Comic Multi-Balloon OCR, Grounding, and Batch Collage Processing with disk evidence.

---

\\mermaid
graph TD
    A[Manga / Comic Chapter Images] --> B[Crop & Pack: 3x3 / 4x4 Grid Collage]
    B --> C[GLM-OCR / GLM-4V Engine]
    C --> D[Structured Output: Text Lines + Box Coordinates]
    D --> E[Unpack & Map: Back to Original Balloon IDs]
    E --> F[Inpaint / Typesetting Downstream Pipeline]
\
---

### Phase 1 — Standalone GLM Comic Pipeline Module
* **Target File:** \ackend/ocr_server/glm_comic_pipeline.py* **Deliverable:** Standalone high-performance engine for:
  1. Direct Single-Balloon OCR & SFX Text Extraction.
  2. Multi-Balloon Grid Packing & Unpacking (Dobkle-style batch collage).
  3. Normalized Bounding Box Coordinate Parser \[0..1000] -> [x, y, w, h]\.

### Phase 2 — Server Integration & Dedicated Endpoints
* **Target File:** \ackend/ocr_server/server.py\ & \ackend/app/ocr_manager.py* **Deliverable:**
  1. Dedicated \/api/ocr/glm\ endpoint with explicit model selection (\zai-org/GLM-OCR\ / \GLM-OCR-Manga-LoRA\).
  2. Batch grid collage OCR endpoint \/api/ocr/glm/batch_grid\.
  3. Structured response schema matching Houmi typography/scanlation pipeline.

### Phase 3 — Real-World Benchmark & Disk Proof on Chapter40_Balloons
* **Target Files:** \C:/Users/dansa/Desktop/Chapter40_Balloons/* **Deliverable:**
  1. Run GLM pipeline on real samples from \Chapter40_Balloons\ (both \Color Hard\ and \Simple No Color\).
  2. Generate structured JSON output + visual contact sheet verifying 100% extraction accuracy without truncation.
  3. Measure VRAM usage (<4GB on RTX 4060) and latency per batch.

### Phase 4 — Verification, Hollow Code Probe & Claim Done
* **Target Actions:** Run full test suite, verify zero stubs/TODOs, and confirm disk evidence bundle.
