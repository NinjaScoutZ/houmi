# Performance Presets API Routes
# backend/app/routes/performance.py

"""
API endpoints for performance preset management.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.performance_presets import (
    list_presets,
    get_preset,
    apply_preset_to_settings,
    get_active_preset_name,
)

router = APIRouter(prefix="/api/performance", tags=["performance"])


class PresetResponse(BaseModel):
    id: str
    name: str
    description: str


class PresetDetailsResponse(BaseModel):
    id: str
    name: str
    description: str
    settings: dict


class ApplyPresetRequest(BaseModel):
    preset_id: str


@router.get("/presets", response_model=list[PresetResponse])
async def get_performance_presets():
    """
    List all available performance presets.

    Returns:
        List of preset metadata (id, name, description)
    """
    presets = list_presets()
    return presets


@router.get("/presets/{preset_id}", response_model=PresetDetailsResponse)
async def get_performance_preset_details(preset_id: str):
    """
    Get detailed configuration for a specific preset.

    Args:
        preset_id: Preset identifier (ultra_fast, balanced, high_quality)

    Returns:
        Preset details including all settings
    """
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")

    return {
        "id": preset_id,
        "name": preset.get("name", preset_id),
        "description": preset.get("description", ""),
        "settings": preset,
    }


@router.post("/presets/apply")
async def apply_performance_preset(request: ApplyPresetRequest):
    """
    Apply a performance preset to current settings.

    Args:
        request: Contains preset_id to apply

    Returns:
        Updated settings with preset applied
    """
    preset_id = request.preset_id

    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")

    # In a real implementation, this would update project settings
    # For now, return the preset settings
    return {
        "success": True,
        "preset_id": preset_id,
        "settings": preset,
        "message": f"Applied preset: {preset.get('name', preset_id)}",
    }
