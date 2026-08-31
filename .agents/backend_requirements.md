# Houmi Studio Backend Requirements & API Spec

> **Document Purpose**: Specifications for backend endpoints, Tauri commands, or IPC bridges required by `frontend_rework/`.  
> **Maintainer**: SUPERVISOR Orchestrator  
> **Last Updated**: 2026-08-30

---

## 📡 Required Endpoints & IPC Contracts

### 1. Hardware & Engine Diagnostics
- **Endpoint**: `GET /api/engine/health`
- **Response**:
  ```json
  {
    "status": "online",
    "gpu_name": "NVIDIA GeForce RTX 4090 / DirectML",
    "optimal_provider": "CUDAExecutionProvider",
    "vram_allocated_mb": 1420,
    "vram_total_mb": 16384,
    "cuda_available": true,
    "directml_available": true
  }
  ```

### 2. Smart Balloon Safe Zone & Centroid Calculation
- **Endpoint**: `POST /api/pipeline/blocks/{block_id}/smart-balloon/recompute`
- **Payload**:
  ```json
  {
    "padding_ratio": 0.1,
    "strict_boundary": true
  }
  ```
- **Response**:
  ```json
  {
    "smart_x": 120.5,
    "smart_y": 340.2,
    "smart_width": 210.0,
    "smart_height": 180.0,
    "smart_mask_path": "M120,340 C..."
  }
  ```

### 3. AI Provider Ping & Diagnostics
- **Endpoint**: `POST /api/ai/test-connection`
- **Payload**:
  ```json
  {
    "provider": "openai" | "gemini" | "anthropic" | "ollama" | "custom",
    "endpoint": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model_name": "gpt-4o"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "latency_ms": 142,
    "available_models": ["gpt-4o", "gpt-4o-mini"],
    "error_message": null
  }
  ```

### 4. Photoshop JSX Character Export Contract
- **Endpoint**: `POST /api/export/photoshop-jsx`
- **Payload**:
  ```json
  {
    "page_id": "page-01",
    "blocks": [
      {
        "id": "block-1",
        "text": "ข้อความภาษาไทย",
        "font_family": "Prompt-Bold",
        "font_size": 24,
        "horizontal_scale": 100,
        "vertical_scale": 100,
        "baseline_shift": 0,
        "tracking": 20,
        "leading": 28,
        "all_caps": false,
        "small_caps": false,
        "underline": false,
        "strikethrough": false
      }
    ]
  }
  ```

---

## 📝 Discovered Backend Requirements Log
*(New requirements identified during Frontend Grill will be logged here)*
