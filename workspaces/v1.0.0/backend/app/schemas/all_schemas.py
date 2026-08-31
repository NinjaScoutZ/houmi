from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

# Text Block Schemas
class TextBlockBase(BaseModel):
    block_index: int
    x: float
    y: float
    width: float
    height: float
    rotation_deg: float = 0.0
    source_text: str = ""
    translation: str = ""
    font_family: str = "NotoSansThai"
    font_size: float = 20.0
    color_hex: str = "#000000"
    bold: bool = False
    italic: bool = False
    text_direction: str = "horizontal"
    text_align: str = "center"
    balloon_type: str = "bubble"
    smart_x: Optional[float] = None
    smart_y: Optional[float] = None
    smart_width: Optional[float] = None
    smart_height: Optional[float] = None
    smart_mask_path: Optional[str] = None

class TextBlockCreate(TextBlockBase):
    pass

class TextBlockUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    block_index: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    smart_x: Optional[float] = None
    smart_y: Optional[float] = None
    smart_width: Optional[float] = None
    smart_height: Optional[float] = None
    smart_mask_path: Optional[str] = None
    rotation_deg: Optional[float] = None
    source_text: Optional[str] = None
    translation: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    color_hex: Optional[str] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    text_direction: Optional[str] = None
    text_align: Optional[str] = None
    balloon_type: Optional[str] = None
    confidence: Optional[float] = None
    extra_metadata: Optional[Dict[str, Any]] = None

    # Custom stroke & glow style fields
    stroke_enabled: Optional[bool] = None
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    outline_glow_enabled: Optional[bool] = None
    outline_glow_color: Optional[str] = None
    outline_glow_radius: Optional[float] = None
    outline_glow_opacity: Optional[float] = None

class TextBlockResponse(TextBlockBase):
    id: str
    page_id: str
    confidence: float
    extra_metadata: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)

# Page Schemas
class PageBase(BaseModel):
    page_number: int
    name: Optional[str] = None

class PageResponse(PageBase):
    id: str
    project_id: str
    width: int
    height: int
    source_image_path: str
    inpainted_image_path: Optional[str] = None
    rendered_image_path: Optional[str] = None
    status: str
    text_blocks: List[TextBlockResponse] = []

    model_config = ConfigDict(from_attributes=True)

# Project Schemas
class ProjectBase(BaseModel):
    name: str
    source_lang: str = "ko"
    target_lang: str = "th"
    settings: Dict[str, Any] = Field(default_factory=dict)

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime
    pages: List[PageResponse] = []

    model_config = ConfigDict(from_attributes=True)

