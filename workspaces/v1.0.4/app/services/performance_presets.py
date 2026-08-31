# Performance Presets Configuration
# backend/app/services/performance_presets.py

"""
Performance optimization presets for different hardware configurations.
Allows users to choose between speed and quality based on their system.
"""

PERFORMANCE_PRESETS = {
    "ultra_fast": {
        "name": "Ultra Fast",
        "description": "⚡ เร็วที่สุด - สำหรับคอม CPU น้อย (Telea, Rectangle Mask)",
        "inpaint_engine": "telea",
        "inpaint_strategy": "per_block",  # Stable for low-end CPUs
        "mask_gen_method": "rectangle",
        "cleanup_mask_strategy": "box",
        "parallel_inpaint_enabled": True,
        "parallel_inpaint_workers": 0,  # Auto-detect based on hardware
        "preview_width": 1200,
        "skip_adaptive_mask": True,
        "use_solid_fill_optimization": True,
        "inpaint_tile_size": 2048,  # Larger tiles = fewer splits
        "mask_dilation_kernel": 2,  # Smaller dilation = faster
    },

    "balanced": {
        "name": "Balanced",
        "description": "⚖️ สมดุล - แนะนำสำหรับคอมทั่วไป (LaMa, Hybrid Mask)",
        "inpaint_engine": "lama",
        "inpaint_strategy": "region",  # Good balance
        "mask_gen_method": "hybrid",
        "cleanup_mask_strategy": "smart",
        "parallel_inpaint_enabled": True,
        "parallel_inpaint_workers": 0,  # Auto-detect based on hardware
        "preview_width": 1600,
        "skip_adaptive_mask": False,
        "use_solid_fill_optimization": True,
        "inpaint_tile_size": 1024,
        "mask_dilation_kernel": 3,
    },

    "high_quality": {
        "name": "High Quality",
        "description": "💎 คุณภาพสูงสุด - ต้องการ GPU (MAT, Adaptive Mask)",
        "inpaint_engine": "mat",
        "inpaint_strategy": "parallel",  # Fastest with GPU
        "mask_gen_method": "hybrid",
        "cleanup_mask_strategy": "smart",
        "parallel_inpaint_enabled": True,
        "parallel_inpaint_workers": 0,  # Auto-detect based on hardware (more workers for GPU)
        "preview_width": 2400,
        "skip_adaptive_mask": False,
        "use_solid_fill_optimization": False,  # Better quality
        "inpaint_tile_size": 1024,
        "mask_dilation_kernel": 3,
    },
}


def get_preset(preset_name: str) -> dict:
    """Get performance preset by name."""
    return PERFORMANCE_PRESETS.get(preset_name, PERFORMANCE_PRESETS["balanced"])


def apply_preset_to_settings(settings: dict, preset_name: str) -> dict:
    """Apply performance preset to project settings."""
    preset = get_preset(preset_name)

    # Create a copy to avoid modifying original
    updated_settings = settings.copy()

    # Apply preset values
    for key, value in preset.items():
        if key not in ("name", "description"):
            updated_settings[key] = value

    # Store which preset is active
    updated_settings["active_performance_preset"] = preset_name

    return updated_settings


def get_active_preset_name(settings: dict) -> str:
    """Get the currently active preset name."""
    return settings.get("active_performance_preset", "balanced")


def list_presets() -> list[dict]:
    """List all available presets with metadata."""
    return [
        {
            "id": preset_id,
            "name": preset["name"],
            "description": preset["description"]
        }
        for preset_id, preset in PERFORMANCE_PRESETS.items()
    ]
