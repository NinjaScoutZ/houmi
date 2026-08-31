"""
Typesetting Rules Manager & Persistence Service
===============================================
Manages linguistic segmentation rules, clitic glueing lists, boundary constraints,
and custom compound dictionaries stored in `e:/houmi/data/thai_typesetting_rules.json`.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Data file path
RULES_DATA_PATH = Path("e:/houmi/data/thai_typesetting_rules.json")
DESKTOP_RESEARCH_PATH = Path("C:/Users/dansa/Desktop/รีเสริช Typeing/thai_typesetting_rules.json")

DEFAULT_TYPESETTING_RULES = {
    "version": "3.0.0",
    "description": "ไฟล์การเรียนรู้และกำหนดกฎไวยากรณ์ภาษาไทยสำหรับ Smart Balloon Typesetting Engine",
    "last_updated": "2026-08-28T00:40:00Z",
    "forward_glue_particles": [
        "ก็", "จะ", "จึง", "ยัง", "มิ", "ไม่", "ได้", "คง", "ย่อม", "ต้อง", "ขอ", "โปรด", "อย่า",
        "หาก", "ถ้า", "ดั่ง", "ประหนึ่ง", "จึ่ง", "ค่อย", "พลัน", "พอ", "เมื่อ", "แม้", "แต่",
        "กว่า", "ราวกับ", "เสมือน", "ดั่งเช่น", "เพียง", "แค่", "ช่าง", "สุด", "โคตร", "บัด",
        "เพิ่ง", "กำลัง", "ชวน", "พลอย", "ล้วน", "ยิ่ง", "แสน", "น่า", "ช่างน่า", "กะ", "แกล้ง",
        "หวัง", "หมาย", "มัว", "ยอม", "ชัก", "ชักจะ", "ดัน", "เผลอ", "เกือบ", "แทบ", "พา",
        "พาให้", "นำ", "คอย", "ตั้งใจ", "พยายาม", "ชวนให้", "เริ่ม", "หัด", "ลอง", "แอบ", "ร่วม"
    ],
    "backward_glue_particles": [
        "นะ", "ล่ะ", "รึ", "หรือ", "สิ", "จัง", "จ้ะ", "จ๋า", "เลย", "ด้วย", "กัน", "เอง",
        "ไหม", "มั้ย", "ครับ", "ค่ะ", "คะ", "หรอก", "เถอะ", "น่า", "หวา", "ว่ะ", "ละ", "เนี่ย",
        "นู่น", "นี่", "นั่น", "เหอะ", "ซะ", "สิเนี่ย", "ซิ", "ซะงั้น", "ไง", "อ่ะ", "จ้า",
        "วะ", "เว้ย", "โว้ย", "ยะ", "ย่ะ", "เนอะ", "เชียว", "ซี", "นา", "เล่า", "ดอก", "เอย",
        "แฮะ", "แฮะๆ", "ฮะ", "ฮะๆ", "จ๊ะ", "จ่ะ", "ซะได้", "ซะนี่", "ไปได้", "มาได้", "เสียได้",
        "จังเลย", "ด้วยสิ", "ไปก่อน", "มาก่อน", "เสียก่อน", "ขึ้นมา", "ลงไป", "เข้าไป", "ออกมา",
        "เสียแล้ว", "ไปแล้ว", "เสียจริง", "เอาไว้", "เข้าไว้", "ซะเลย", "ดูสิ", "ดูนะ", "ดูซิ",
        "ทีเดียว", "ซะด้วย", "บ้าง", "ล่ะเนี่ย", "ซะงั้นนะ", "แหละ", "หว่า", "นั่นแหละ", "นี่นา", "นู่นแน่ะ"
    ],
    "never_start_line": [
        "ก็", "นะ", "ล่ะ", "รึ", "หรือ", "สิ", "จัง", "เลย", "ด้วย", "กัน", "ไหม", "มั้ย",
        "ครับ", "ค่ะ", "คะ", "หรอก", "เถอะ", "ๆ", "ฯ", "!", "?", "...", "!!", "?!", "!?",
        "!!!", "??", "”", "’", ")", "]", "}", "》", "」", "』", "】", "”", "’",
        "-", "–", "—", "ฯลฯ", "แหละ", "หว่า", "ว่ะ", "เว้ย", "โว้ย", "แฮะ", "ไง", "ซะ",
        "เหอะ", "ดอก", "เอย", "เนี่ย", "นี่นา", "ล่ะเนี่ย", "จังเลย", "ซะด้วย", "ทีเดียว"
    ],
    "never_end_line": [
        "ก็", "จะ", "จึง", "ที่", "ซึ่ง", "อัน", "ว่า", "แต่", "เพราะ", "ณ", "แด่", "แก่",
        "ต่อ", "สู่", "ยัง", "บน", "ใต้", "ใน", "นอก", "ระหว่าง", "เพื่อ", "สำหรับ", "เนื่องจาก",
        "หากว่า", "ถ้าหาก", "“", "‘", "(", "[", "{", "《", "「", "『", "【", "ราวกับ",
        "เสมือน", "ดั่งเช่น", "เหมือนดัง", "คล้ายกับ", "กำลัง", "เพิ่ง", "แอบ", "เริ่ม", "คอย", "ตั้ง"
    ],
    "custom_compound_words": [
        "นายน้อยฉางเกอ", "องค์เทพประมุข", "ราชวงศ์เซียนอู๋ซวง", "สวรรค์ทมิฬ", "กู้ฉางเกอ",
        "ทำเนียบ", "มหาบุรุษ", "รากฐาน", "อัครเทวทูต", "บัลลังก์ธาตุ", "ร็อดเจอร์ส",
        "โคบิกสตูดิโอ", "กเวมุล", "ทัลยอง", "อีซองชี", "หน่วยผู้คุมกฎ", "ผู้ท่องวิญญาณ",
        "ชานเมืองซากปรักหักพังจินหลิง", "เคล็ดวิชาเก้าจิ่วอี๋แผดเผานภา", "แม่ทัพแห่งราคะ",
        "ดันเจี้ยนยูหลิงชั้นใต้ดิน", "เมล็ดพันธุ์มารไร้ลักษณ์โดยกำเนิด", "สถานสงเคราะห์เด็กกำพร้าซินฮั่ว",
        "ปรมาจารย์สวรรค์โบราณอวี่ฮว่า", "ค่ายกลกระชากวิญญาณกระตุ้นตัณหา", "กิ้งก่ายักษ์กระดูกผุ"
    ],
    "unbreakable_phrases": [
        "อะไรนะ!?", "เป็นไปไม่ได้!", "อย่าบอกนะว่า...", "บ้าเอ๊ย!", "หนอยแน่ะ!", "ช่วยด้วย!",
        "ตายซะเถอะ!", "ช่างเถอะ", "ไม่เป็นไร", "ว่าไงนะ!?", "เจ้าบ้านี่!", "โกหกน่า...",
        "ให้ตายสิ", "ไม่จริงใช่ไหม", "ข้าไม่ยอมแพ้", "ไปตายซะ!", "ล้อเล่นน่า", "ช่วยไม่ได้แฮะ",
        "จริงดิ!?", "ชักจะทนไม่ไหวแล้วนะ!", "เป็นไปไม่ได้น่า!", "อย่าเข้ามานะ!!", "ถอยออกไปเดี๋ยวนี้!",
        "ไม่มีทาง!", "พูดเป็นเล่นน่า!", "ตั้งแต่เมื่อไหร่กัน!?", "ยอมแพ้ซะเถอะ!", "อย่ามาดูถูกกันนะ!",
        "เจ้าบ้าเอ๊ย!", "ขอร้องล่ะ!", "ไม่คิดเลยว่า...", "อย่าเข้าใจผิดนะ!", "อย่างนี้นี่เอง",
        "ไม่ว่ายังไงก็...", "นึกไม่ถึงเลยว่า...", "ช่างน่าเสียดาย", "ไม่เอาด้วยหรอก", "ยินดีด้วยนะ",
        "ทำไมถึงเป็นแบบนี้", "ไม่มีวันยกโทษให้แน่!", "เอาจริงดิ!?", "ฝันไปเถอะ!", "เรื่องแบบนั้นมัน...",
        "ขอโทษด้วยนะ", "ขอบคุณมากนะ", "เตรียมใจไว้เถอะ!", "อย่าหนีนะ!", "คิดจะทำอะไรน่ะ!?",
        "หนอยแก!", "ไอ้สารเลว!", "บ้าที่สุด!", "อย่าทำแบบนี้นะ", "เชื่อใจฉันเถอะ", "เก่งมากเลยนะ",
        "สุดยอดไปเลย!", "อย่ามายุ่ง!", "หลบไป!", "ระวังตัวด้วยนะ", "ไม่มีปัญหา!", "ชักจะสนุกขึ้นมาแล้วสิ",
        "ไม่ไหวแล้ว...", "ทำได้ดีมาก", "ตามมานี่!", "ปล่อยฉันนะ!", "รู้แล้วน่า", "ว่าไปนั่น",
        "จริงด้วยสิ", "ช่างมันเถอะนะ", "เข้าใจแล้วล่ะ", "เป็นความจริงหรือ", "ไม่เคยโจมตี", "ขอยินยอมสยบ"
    ]
}

class TypesettingRulesModel(BaseModel):
    version: str = "2.0.0"
    description: str = "Typesetting Rules Configuration"
    last_updated: Optional[str] = None
    forward_glue_particles: List[str] = Field(default_factory=list)
    backward_glue_particles: List[str] = Field(default_factory=list)
    never_start_line: List[str] = Field(default_factory=list)
    never_end_line: List[str] = Field(default_factory=list)
    custom_compound_words: List[str] = Field(default_factory=list)
    unbreakable_phrases: List[str] = Field(default_factory=list)

class RuleTestRequest(BaseModel):
    sample_text: str
    target_lines: int = 3
    custom_rules: Optional[TypesettingRulesModel] = None

class RuleTestResponse(BaseModel):
    sample_text: str
    tokens: List[str]
    split_lines: List[str]
    applied_forward_glues: List[str]
    applied_backward_glues: List[str]
    triggered_rules: List[str]

_CACHED_RULES: Optional[Dict[str, Any]] = None

def get_typesetting_rules() -> Dict[str, Any]:
    """Retrieves active typesetting rules from data storage, falling back to defaults."""
    global _CACHED_RULES
    if _CACHED_RULES is not None:
        return _CACHED_RULES

    # Ensure parent dir exists
    RULES_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if RULES_DATA_PATH.exists():
        try:
            with open(RULES_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _CACHED_RULES = data
                return data
        except Exception as e:
            logger.warning(f"Failed to read {RULES_DATA_PATH}: {e}. Falling back to default rules.")
    
    # Save default if not existing
    save_typesetting_rules(DEFAULT_TYPESETTING_RULES)
    _CACHED_RULES = DEFAULT_TYPESETTING_RULES
    return DEFAULT_TYPESETTING_RULES

def save_typesetting_rules(rules: Dict[str, Any]) -> bool:
    """Saves updated typesetting rules to storage and invalidates tokenizer cache."""
    global _CACHED_RULES
    try:
        RULES_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RULES_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        
        # Sync to Desktop Research folder if available
        if DESKTOP_RESEARCH_PATH.parent.exists():
            try:
                with open(DESKTOP_RESEARCH_PATH, "w", encoding="utf-8") as df:
                    json.dump(rules, df, ensure_ascii=False, indent=2)
            except Exception:
                pass

        _CACHED_RULES = rules
        logger.info("Typesetting rules saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving typesetting rules: {e}")
        return False

def reset_typesetting_rules_to_default() -> Dict[str, Any]:
    """Resets typesetting rules back to factory default configuration."""
    save_typesetting_rules(DEFAULT_TYPESETTING_RULES)
    return DEFAULT_TYPESETTING_RULES

def simulate_rules_evaluation(sample_text: str, target_lines: int = 3, rules_dict: Optional[Dict[str, Any]] = None) -> RuleTestResponse:
    """
    Simulates token segmentation and line breaking on arbitrary input text
    using either active rules or custom playground rules.
    """
    if rules_dict is None:
        rules_dict = get_typesetting_rules()

    from app.services.typesetting.segmentation import segment_text
    
    f_particles = set(rules_dict.get("forward_glue_particles", []))
    b_particles = set(rules_dict.get("backward_glue_particles", []))
    compounds = rules_dict.get("custom_compound_words", [])
    
    # Perform segmentation with rules
    tokens = segment_text(sample_text, project_dictionary=compounds)
    
    # Analyze triggered rules
    applied_f = []
    applied_b = []
    triggered = []
    
    for t in tokens:
        for fp in f_particles:
            if t.startswith(fp) and len(t) > len(fp):
                applied_f.append(f"'{fp}' glued in '{t}'")
                triggered.append(f"Forward Glue: {fp} ➔ {t}")
        for bp in b_particles:
            if t.endswith(bp) and len(t) > len(bp):
                applied_b.append(f"'{bp}' glued in '{t}'")
                triggered.append(f"Backward Glue: {bp} ➔ {t}")
        for comp in compounds:
            if comp in t:
                triggered.append(f"Compound Word Preserved: '{comp}'")
                
    # Simple line split simulation
    split_lines = []
    if len(tokens) <= target_lines:
        split_lines = tokens
    else:
        chunk_size = max(1, len(tokens) // target_lines)
        for i in range(0, len(tokens), chunk_size):
            line = "".join(tokens[i : i + chunk_size]).strip()
            if line:
                split_lines.append(line)
                
    return RuleTestResponse(
        sample_text=sample_text,
        tokens=tokens,
        split_lines=split_lines,
        applied_forward_glues=list(set(applied_f)),
        applied_backward_glues=list(set(applied_b)),
        triggered_rules=list(set(triggered))
    )


def get_slang_dictionary_stats() -> Dict[str, Any]:
    """Returns statistics about the active manga and novel slang dictionary."""
    from app.services.typesetting.segmentation import SLANG_DATA_PATH, _load_slang_words
    words = _load_slang_words()
    return {
        "path": str(SLANG_DATA_PATH),
        "exists": SLANG_DATA_PATH.exists(),
        "total_terms": len(words),
        "sample": sorted(list(words), key=lambda x: -len(x))[:10] if words else []
    }
