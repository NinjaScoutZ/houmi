"""
Manga & Webtoon Sound Effects (SFX) Dictionary Service for Houmi Studio.
Provides multi-language onomatopoeia translation, categorization, and phonetic mappings.
"""
from typing import List, Dict, Any, Optional
import re

SFX_DATABASE: List[Dict[str, Any]] = [
    # --- Impact & Explosions ---
    {"orig": "ドドド", "lang": "ja", "romaji": "dododo", "thai": "ตึกตัก / ครืนครืน", "category": "motion", "meaning": "เสียงฝีเท้าวิ่งกรูกันเข้ามา หรือเสียงแผ่นดินไหว/แรงกดดัน"},
    {"orig": "ドカン", "lang": "ja", "romaji": "dokan", "thai": "ตู้มมม!", "category": "impact", "meaning": "เสียงระเบิดเสียงดังสนั่น"},
    {"orig": "バン", "lang": "ja", "romaji": "ban", "thai": "ปัง!", "category": "impact", "meaning": "เสียงกระแทก ยิงปืน หรือปิดประตูดัง"},
    {"orig": "バキッ", "lang": "ja", "romaji": "baki", "thai": "กร๊อบ!", "category": "impact", "meaning": "เสียงกระดูกหัก หรือของแข็งหักสะบั้น"},
    {"orig": "ズガガ", "lang": "ja", "romaji": "zugaga", "thai": "ครืนนน!", "category": "impact", "meaning": "เสียงถล่มทลายรุนแรง"},
    {"orig": "パシッ", "lang": "ja", "romaji": "pashi", "thai": "เพียะ!", "category": "impact", "meaning": "เสียงตบ หรือรับของได้อย่างแม่นยำ"},
    {"orig": "ゴゴゴ", "lang": "ja", "romaji": "gogogo", "thai": "โกโกโก / ครืนนน", "category": "ambient", "meaning": "บรรยากาศน่าสะพรึงกลัว ออร่าคุกคามทรงพลัง"},
    {"orig": "ザッ", "lang": "ja", "romaji": "za", "thai": "ฟึ่บ / ขวับ", "category": "motion", "meaning": "เสียงก้าวเดินอย่างมั่นคง หรือหยุดชะงักอย่างรวดเร็ว"},
    {"orig": "シュッ", "lang": "ja", "romaji": "shu", "thai": "ฟิ้ว / ฟึ่บ", "category": "motion", "meaning": "เสียงพุ่งตัวด้วยความเร็วสูง"},
    {"orig": "ドキドキ", "lang": "ja", "romaji": "dokidoki", "thai": "ตึกตัก ตึกตัก", "category": "emotion", "meaning": "เสียงหัวใจเต้นแรงด้วยความตื่นเต้นหรือกังวล"},
    {"orig": "ニコッ", "lang": "ja", "romaji": "niko", "thai": "ยิ้มมม", "category": "emotion", "meaning": "ยิ้มหวาน หรือยิ้มแย้มแจ่มใส"},
    {"orig": "ギラッ", "lang": "ja", "romaji": "gira", "thai": "วาบ / วาวโรจน์", "category": "magic", "meaning": "สายตาหรืออาวุธเปล่งประกายคมกริบ"},
    
    # --- Korean Webtoon SFX ---
    {"orig": "쿠구구", "lang": "ko", "romaji": "kugugu", "thai": "ครืนนน ครืนนน", "category": "ambient", "meaning": "เสียงแผ่นดินสั่นสะเทือนหรือพลังงานปะทุ"},
    {"orig": "콰쾅", "lang": "ko", "romaji": "kwakwang", "thai": "เปรี้ยงงง / ตู้มมม!", "category": "impact", "meaning": "เสียงระเบิดหรือการปะทะกันอย่างรุนแรง"},
    {"orig": "팍", "lang": "ko", "romaji": "pak", "thai": "ผลัวะ!", "category": "impact", "meaning": "เสียงชกหรือฟาดเข้าเป้าอย่างแรง"},
    {"orig": "슥", "lang": "ko", "romaji": "seuk", "thai": "สวบ / สวบสาบ", "category": "motion", "meaning": "เสียงเคลื่อนไหวเงียบๆ หรือชักดาบ"},
    {"orig": "샤อา", "lang": "ko", "romaji": "shaaa", "thai": "ซู่ววว", "category": "ambient", "meaning": "เสียงสายฝน พลังเวทมนตร์ หรือลมพัด"},
    {"orig": "콰아아", "lang": "ko", "romaji": "kwaaa", "thai": "ซ่าาา / ซู่ววว", "category": "magic", "meaning": "คลื่นพลังเวทมนตร์หรือเปลวเพลิงแผ่ขยาย"},
    {"orig": "두근두근", "lang": "ko", "romaji": "dugeundugeun", "thai": "ตึกตัก ตึกตัก", "category": "emotion", "meaning": "เสียงหัวใจเต้นรัว"},
    {"orig": "피식", "lang": "ko", "romaji": "pisik", "thai": "หึ...", "category": "emotion", "meaning": "ยิ้มเยาะหรือหัวเราะในลำคอ"},

    # --- Chinese Manhua SFX ---
    {"orig": "轰", "lang": "zh", "romaji": "hong", "thai": "ตู้มมม!", "category": "impact", "meaning": "เสียงระเบิดกึกก้อง"},
    {"orig": "砰", "lang": "zh", "romaji": "peng", "thai": "ปัง!", "category": "impact", "meaning": "เสียงกระแทกดัง"},
    {"orig": "啪", "lang": "zh", "romaji": "pa", "thai": "เพียะ / แปะ", "category": "impact", "meaning": "เสียงตบมือ หรือตบหน้า"},
    {"orig": "呼", "lang": "zh", "romaji": "hu", "thai": "ฟู่ / ฟิ้ว", "category": "motion", "meaning": "เสียงพัดของกระแสลมหรือถอนหายใจ"},
    {"orig": "嗖", "lang": "zh", "romaji": "sou", "thai": "เฟี้ยววว", "category": "motion", "meaning": "เสียงวัตถุพุ่งผ่านอากาศด้วยความเร็วสูง"},
    {"orig": "嗡", "lang": "zh", "romaji": "weng", "thai": "หึ่งงง / วิ้งงง", "category": "magic", "meaning": "เสียงพลังงานสั่นสะเทือน หรือเสียงสะท้อน"},
    {"orig": "咚", "lang": "zh", "romaji": "dong", "thai": "ตึก / ตึง", "category": "impact", "meaning": "เสียงทุบของหนักลงพื้น หรือเสียงกลอง"},
    {"orig": "咔嚓", "lang": "zh", "romaji": "kacha", "thai": "แชะ / แกร๊ก", "category": "motion", "meaning": "เสียงถ่ายรูป หรือเสียงเปิดกลไก"},
]


def lookup_sfx(query: str, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search SFX database by exact match, substring match, or romaji.
    """
    if not query:
        return []
    
    q_norm = query.strip().lower()
    results = []

    for item in SFX_DATABASE:
        if lang and lang != "auto" and item["lang"] != lang.lower():
            continue

        orig = item["orig"].lower()
        romaji = item["romaji"].lower()
        thai = item["thai"].lower()

        # Exact match gets highest priority
        if q_norm == orig or q_norm == romaji or q_norm in orig:
            results.append(item)

    return results


def suggest_sfx_translation(source_text: str) -> Optional[str]:
    """
    Quickly suggest a Thai sound effect translation for given OCR text.
    """
    if not source_text:
        return None
    
    clean_src = re.sub(r'[^\w\s]', '', source_text.strip())
    matches = lookup_sfx(clean_src)
    if matches:
        return matches[0]["thai"]
    
    return None


def get_sfx_catalog(category: Optional[str] = None, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get full list of SFX presets filtered by category or language.
    """
    filtered = SFX_DATABASE
    if category:
        filtered = [item for item in filtered if item["category"] == category.lower()]
    if lang and lang != "auto":
        filtered = [item for item in filtered if item["lang"] == lang.lower()]
    return filtered
