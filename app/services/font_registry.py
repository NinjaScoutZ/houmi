import os
import re
import hashlib
import logging
import struct
from pathlib import Path
from dataclasses import dataclass, field, replace
from typing import Optional, List, Dict, Tuple
from PIL import ImageFont

logger = logging.getLogger("houmi-font-registry")

@dataclass
class FontRegistryEntry:
    stable_id: str
    family: str
    postscript_name: str
    file_path: Path
    style: str  # regular, bold, italic, bold_italic
    fingerprint: str
    is_fallback: bool = False
    weight: int = 400
    full_name: str = ""
    css_style: str = "normal"  # normal, italic
    category: str = "system"   # bundled, custom, manga, thai, system
    supports_thai: bool = False
    file_size: int = 0

@dataclass
class FontFamilyInfo:
    family: str
    category: str
    variants: Dict[str, FontRegistryEntry] = field(default_factory=dict)
    default_style: str = "regular"

def get_file_fingerprint(path: Path) -> str:
    """Generates a stable fingerprint of the font file by hashing its content."""
    if not path.exists():
        return "missing"
    try:
        sha256 = hashlib.sha256()
        # Hash only the first 64KB for speed
        with open(path, "rb") as f:
            chunk = f.read(65536)
            sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to calculate hash for {path}: {e}")
        return "error"

class FontRegistry:
    def __init__(self):
        self.registry: dict[str, FontRegistryEntry] = {}
        self.variants_by_id: dict[str, FontRegistryEntry] = {}
        self.families: dict[str, FontFamilyInfo] = {}
        self.aliases: dict[str, tuple[str, str]] = {}
        self._clean_aliases: dict[str, tuple[str, str]] = {}
        self._warned_fonts: set[str] = set()
        self.windows_fonts_dir = Path("C:/Windows/Fonts")
        self._custom_font_dirs: list[Path] = []
        self._initialize_registry()

    @staticmethod
    def _clean_font_key(s: str) -> str:
        """Normalizes font name by stripping symbols and canonicalizing common spelling variations."""
        cleaned = re.sub(r"[^a-z0-9]", "", str(s or "").lower())
        # Canonicalize known comic font phonetic / spelling variations
        cleaned = cleaned.replace("phethai", "phetai").replace("phentai", "phetai")
        cleaned = cleaned.replace("tarminetine", "tamaitine").replace("tarmintine", "tamaitine")
        cleaned = cleaned.replace("v10", "v1").replace("ver10", "v1").replace("ver101", "v1")
        return cleaned

    def _get_file_fingerprint(self, path: Path) -> str:
        return get_file_fingerprint(path)

    @staticmethod
    def _read_sfnt_tables(data: bytes, base_offset: int = 0) -> dict[bytes, tuple[int, int]]:
        """Reads SFNT directory tables (tag -> (offset, length))."""
        try:
            if len(data) < base_offset + 12:
                return {}
            table_count = struct.unpack_from(">H", data, base_offset + 4)[0]
            tables = {}
            for index in range(table_count):
                entry_offset = base_offset + 12 + index * 16
                if len(data) < entry_offset + 16:
                    break
                tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, entry_offset)
                tables[tag] = (offset, length)
            return tables
        except (struct.error, IndexError):
            return {}

    @classmethod
    def _read_sfnt_names_and_weight(cls, font_file: Path) -> list[dict]:
        """
        Reads family, subfamily, full name, PostScript name, weight, and Thai support
        from a .ttf, .otf, or .ttc file without heavy external dependencies.
        """
        try:
            data = font_file.read_bytes()
            if len(data) < 12:
                return []

            offsets = [0]
            if data[:4] == b"ttcf":
                # TrueType Collection: parse all font offsets
                if len(data) >= 12:
                    num_fonts = struct.unpack_from(">I", data, 8)[0]
                    offsets = [
                        struct.unpack_from(">I", data, 12 + i * 4)[0]
                        for i in range(min(num_fonts, 32))
                        if len(data) >= 16 + i * 4
                    ]

            results = []
            for base in offsets:
                tables = cls._read_sfnt_tables(data, base)
                name_info = tables.get(b"name")
                if not name_info:
                    continue

                name_offset, _ = name_info
                if len(data) < name_offset + 6:
                    continue
                _format, count, string_offset = struct.unpack_from(">HHH", data, name_offset)
                
                candidates: dict[int, list[tuple[int, str]]] = {}
                for index in range(count):
                    record_offset = name_offset + 6 + index * 12
                    if len(data) < record_offset + 12:
                        break
                    platform, _encoding, language, name_id, length, offset = struct.unpack_from(
                        ">HHHHHH", data, record_offset
                    )
                    # 1: Family, 2: Subfamily, 4: Full Name, 6: PostScript Name, 16: Typographic Family, 17: Typographic Subfamily
                    if name_id not in (1, 2, 4, 6, 16, 17):
                        continue
                    start = name_offset + string_offset + offset
                    if len(data) < start + length:
                        continue
                    raw = data[start:start + length]
                    try:
                        value = raw.decode("utf-16-be" if platform in (0, 3) else "mac_roman")
                    except (UnicodeDecodeError, LookupError):
                        continue
                    value = value.strip("\x00 \t\r\n")
                    if value:
                        score = (4 if platform == 3 else 2) + (2 if language in (0, 0x409) else 0)
                        candidates.setdefault(name_id, []).append((score, value))

                extracted_names = {
                    name_id: max(values, key=lambda item: item[0])[1]
                    for name_id, values in candidates.items()
                    if values
                }

                # Read OS/2 table for weight & selection flags if present
                weight = 400
                is_italic_flag = False
                os2_info = tables.get(b"OS/2")
                if os2_info:
                    os2_offset, _ = os2_info
                    if len(data) >= os2_offset + 64:
                        us_weight = struct.unpack_from(">H", data, os2_offset + 4)[0]
                        if 100 <= us_weight <= 900:
                            weight = us_weight
                        fs_selection = struct.unpack_from(">H", data, os2_offset + 62)[0]
                        is_italic_flag = bool(fs_selection & 1)

                # Check cmap table for Thai Unicode range (0x0E00 - 0x0E7F)
                supports_thai = False
                cmap_info = tables.get(b"cmap")
                if cmap_info:
                    # Quick heuristic scan in cmap for Thai character coverage
                    try:
                        supports_thai = b"\x0e\x01" in data or "thai" in font_file.name.lower() or "sukhumvit" in font_file.name.lower() or "sarabun" in font_file.name.lower()
                    except Exception:
                        pass

                results.append({
                    "names": extracted_names,
                    "weight": weight,
                    "is_italic": is_italic_flag,
                    "supports_thai": supports_thai
                })

            return results
        except Exception as e:
            logger.debug(f"SFNT parsing failed for {font_file}: {e}")
            return []

    @classmethod
    def _classify_style(cls, *values: str, weight: int = 400, is_italic: bool = False) -> str:
        normalized = " ".join(str(value or "") for value in values).lower()
        normalized = normalized.replace("-", " ").replace("_", " ")
        has_bold = "bold" in normalized or "black" in normalized or "heavy" in normalized or weight >= 700
        has_italic = "italic" in normalized or "oblique" in normalized or is_italic
        if has_bold and has_italic:
            return "bold_italic"
        if has_bold:
            return "bold"
        if has_italic:
            return "italic"
        return "regular"

    def register_entry(self, entry: FontRegistryEntry, category: str = "system"):
        """Registers a FontRegistryEntry into registry, families, and alias maps."""
        entry.category = category
        fam_key = entry.family.lower().strip()
        style_key = f"{fam_key}_{entry.style}"
        
        # Save to primary registry with canonical weight precedence
        existing = self.registry.get(style_key)
        should_replace = True
        if existing:
            if entry.style == "bold":
                existing_diff = abs(existing.weight - 700)
                new_diff = abs(entry.weight - 700)
                if new_diff > existing_diff:
                    should_replace = False
                elif new_diff == existing_diff and "black" in entry.postscript_name.lower():
                    should_replace = False
            elif entry.style == "regular":
                existing_diff = abs(existing.weight - 400)
                new_diff = abs(entry.weight - 400)
                if new_diff > existing_diff:
                    should_replace = False

        if should_replace:
            self.registry[style_key] = entry

        self.variants_by_id[entry.stable_id.lower()] = entry
        if entry.postscript_name:
            self.variants_by_id[entry.postscript_name.lower()] = entry

        # Add to family grouping
        if fam_key not in self.families:
            self.families[fam_key] = FontFamilyInfo(
                family=entry.family,
                category=category,
                variants={},
                default_style=entry.style
            )
        self.families[fam_key].variants[entry.style] = entry
        if entry.style == "regular":
            self.families[fam_key].default_style = "regular"

        # Build comprehensive raw aliases
        self.aliases[entry.stable_id.lower()] = (entry.family, entry.style)
        if entry.postscript_name:
            self.aliases[entry.postscript_name.lower()] = (entry.family, entry.style)
        if entry.full_name:
            self.aliases[entry.full_name.lower()] = (entry.family, entry.style)
        if fam_key not in self.aliases or entry.style == "regular":
            self.aliases[fam_key] = (entry.family, entry.style)

        # Build smart clean aliases for resilient matching across spelling variations
        for candidate in [
            entry.family,
            entry.full_name,
            entry.postscript_name,
            entry.stable_id,
            entry.file_path.stem if entry.file_path else "",
        ]:
            ck = self._clean_font_key(candidate)
            if ck:
                self._clean_aliases[ck] = (entry.family, entry.style)
                if ck.startswith("th") and len(ck) > 3:
                    self._clean_aliases[ck[2:]] = (entry.family, entry.style)
                for suffix in ["regular", "bold", "medium", "demo", "v1"]:
                    if ck.endswith(suffix) and len(ck) > len(suffix) + 2:
                        self._clean_aliases[ck[:-len(suffix)]] = (entry.family, entry.style)

    def register_font_file(self, font_file: Path, category: str = "custom") -> List[FontRegistryEntry]:
        """Registers an individual font file, parsing all faces and adding them to registry."""
        if not font_file.exists():
            return []
        
        ext = font_file.suffix.lower()
        if ext not in (".ttf", ".otf", ".ttc", ".woff2"):
            return []

        entries = []
        parsed_faces = self._read_sfnt_names_and_weight(font_file)
        file_fingerprint = self._get_file_fingerprint(font_file)
        file_size = font_file.stat().st_size if font_file.exists() else 0

        if parsed_faces:
            for idx, face in enumerate(parsed_faces):
                names = face.get("names", {})
                weight = face.get("weight", 400)
                is_italic = face.get("is_italic", False)
                supports_thai = face.get("supports_thai", False)

                family = names.get(16) or names.get(1) or font_file.stem
                subfamily = names.get(17) or names.get(2) or "Regular"
                full_name = names.get(4) or f"{family} {subfamily}".strip()
                postscript_name = names.get(6) or family.replace(" ", "")

                style = self._classify_style(subfamily, postscript_name, font_file.stem, weight=weight, is_italic=is_italic)
                css_style = "italic" if "italic" in style else "normal"
                stable_id = f"{font_file.stem}_{idx}_{style}".lower() if len(parsed_faces) > 1 else f"{font_file.stem}_{style}".lower()

                entry = FontRegistryEntry(
                    stable_id=stable_id,
                    family=family,
                    postscript_name=postscript_name,
                    file_path=font_file,
                    style=style,
                    fingerprint=file_fingerprint,
                    weight=weight,
                    full_name=full_name,
                    css_style=css_style,
                    category=category,
                    supports_thai=supports_thai,
                    file_size=file_size
                )
                self.register_entry(entry, category=category)
                entries.append(entry)
        else:
            # Fallback ImageFont name reading
            try:
                family, subfamily = ImageFont.truetype(str(font_file), 12).getname()
                family = str(family).strip() or font_file.stem
                subfamily = str(subfamily or "Regular").strip()
                style = self._classify_style(subfamily, font_file.stem)
                postscript_name = f"{family.replace(' ', '')}-{style.title()}"
                stable_id = f"{font_file.stem}_{style}".lower()

                entry = FontRegistryEntry(
                    stable_id=stable_id,
                    family=family,
                    postscript_name=postscript_name,
                    file_path=font_file,
                    style=style,
                    fingerprint=file_fingerprint,
                    weight=700 if "bold" in style else 400,
                    full_name=f"{family} {subfamily}".strip(),
                    css_style="italic" if "italic" in style else "normal",
                    category=category,
                    supports_thai="thai" in font_file.name.lower(),
                    file_size=file_size
                )
                self.register_entry(entry, category=category)
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Could not load font metadata from {font_file}: {e}")

        return entries

    def _initialize_registry(self):
        """Scans standard system font paths, bundled fonts, and custom fonts."""
        # 1. Standard bundled fonts mapping
        standard_fonts = [
            ("tahoma", "Tahoma", "Tahoma", "tahoma.ttf", "regular", 400),
            ("tahomabd", "Tahoma", "Tahoma-Bold", "tahomabd.ttf", "bold", 700),
            ("arial", "Arial", "ArialMT", "arial.ttf", "regular", 400),
            ("arialbd", "Arial", "Arial-BoldMT", "arialbd.ttf", "bold", 700),
            ("ariali", "Arial", "Arial-ItalicMT", "ariali.ttf", "italic", 400),
            ("arialbi", "Arial", "Arial-BoldItalicMT", "arialbi.ttf", "bold_italic", 700),
            ("calibri", "Calibri", "Calibri", "calibri.ttf", "regular", 400),
            ("calibrib", "Calibri", "Calibri-Bold", "calibrib.ttf", "bold", 700),
            ("calibrii", "Calibri", "Calibri-Italic", "calibrii.ttf", "italic", 400),
            ("calibriz", "Calibri", "Calibri-BoldItalic", "calibriz.ttf", "bold_italic", 700),
            ("notosansthai", "Noto Sans Thai", "NotoSansThai-Regular", "NotoSansThai-Regular.ttf", "regular", 400),
            ("notosansthaibd", "Noto Sans Thai", "NotoSansThai-Bold", "NotoSansThai-Bold.ttf", "bold", 700),
        ]

        # Search standard directories
        search_dirs = [Path(".")]
        if self.windows_fonts_dir.exists():
            search_dirs.append(self.windows_fonts_dir)
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            user_fonts_dir = Path(local_appdata) / "Microsoft" / "Windows" / "Fonts"
            if user_fonts_dir.exists():
                search_dirs.append(user_fonts_dir)

        # Check bundled / custom folders
        bundled_dir = Path("backend/assets/fonts")
        if bundled_dir.exists():
            search_dirs.append(bundled_dir)
            self._custom_font_dirs.append(bundled_dir)
        
        custom_data_dir = Path("data/fonts")
        if custom_data_dir.exists():
            search_dirs.append(custom_data_dir)
            self._custom_font_dirs.append(custom_data_dir)

        for font_id, family, ps_name, filename, style, weight in standard_fonts:
            resolved_path = None
            for sdir in search_dirs:
                test_path = sdir / filename
                if test_path.exists():
                    resolved_path = test_path
                    break
            
            if resolved_path:
                fingerprint = self._get_file_fingerprint(resolved_path)
                entry = FontRegistryEntry(
                    stable_id=font_id,
                    family=family,
                    postscript_name=ps_name,
                    file_path=resolved_path,
                    style=style,
                    fingerprint=fingerprint,
                    weight=weight,
                    full_name=f"{family} {style.title()}",
                    css_style="italic" if "italic" in style else "normal",
                    category="bundled" if "noto" in family.lower() else "system",
                    supports_thai="thai" in family.lower() or "tahoma" in family.lower(),
                    file_size=resolved_path.stat().st_size if resolved_path.exists() else 0
                )
                self.register_entry(entry, category=entry.category)

        # Scan all .ttf, .otf, and .ttc files in directories
        font_dirs = []
        if self.windows_fonts_dir.exists():
            font_dirs.append(self.windows_fonts_dir)
        if local_appdata:
            user_fonts_dir = Path(local_appdata) / "Microsoft" / "Windows" / "Fonts"
            if user_fonts_dir.exists():
                font_dirs.append(user_fonts_dir)
        font_dirs.extend(self._custom_font_dirs)

        for font_dir in font_dirs:
            if not font_dir.exists():
                continue
            for font_file in font_dir.iterdir():
                ext = font_file.suffix.lower()
                if ext not in (".ttf", ".otf", ".ttc"):
                    continue
                stem = font_file.stem.lower()
                if stem in self.aliases:
                    continue
                category = "custom" if font_dir in self._custom_font_dirs else "system"
                self.register_font_file(font_file, category=category)

    def scan_custom_directory(self, directory: Path):
        """Scans an additional custom fonts directory (e.g. project-specific fonts)."""
        if not directory.exists() or not directory.is_dir():
            return
        if directory not in self._custom_font_dirs:
            self._custom_font_dirs.append(directory)
        for font_file in directory.iterdir():
            if font_file.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff2"):
                self.register_font_file(font_file, category="custom")

    def rescan(self) -> list[str]:
        """Clears cached registry state and rescans all font directories dynamically."""
        self.registry.clear()
        self.variants_by_id.clear()
        self.families.clear()
        self.aliases.clear()
        self._clean_aliases.clear()
        self._warned_fonts.clear()
        self._custom_font_dirs.clear()
        self._initialize_registry()
        logger.info("Rescanned fonts: found %d families, %d variants", len(self.families), len(self.variants_by_id))
        return self.list_families()

    def list_families(self) -> list[str]:
        """Returns a sorted list of unique font family names from the registry."""
        families = set()
        for entry in self.registry.values():
            families.add(entry.family)
        return sorted(families)

    def get_family_details(self) -> dict:
        """Returns detailed family metadata for frontend consumption."""
        result = {}
        for fam_key, info in self.families.items():
            result[info.family] = {
                "family": info.family,
                "category": info.category,
                "styles": sorted(list(info.variants.keys())),
                "variants": [
                    {
                        "variant_id": v.stable_id,
                        "style": v.style,
                        "weight": v.weight,
                        "css_style": v.css_style,
                        "postscript_name": v.postscript_name,
                        "full_name": v.full_name,
                        "supports_thai": v.supports_thai,
                        "file_size": v.file_size
                    }
                    for v in info.variants.values()
                ]
            }
        return result

    def get_variant_by_id(self, variant_id: str) -> Optional[FontRegistryEntry]:
        """Finds font variant entry by variant_id or PostScript name."""
        norm_id = variant_id.lower().strip()
        if norm_id in self.variants_by_id:
            return self.variants_by_id[norm_id]
        if norm_id in self.aliases:
            fam, style = self.aliases[norm_id]
            return self.registry.get(f"{fam.lower()}_{style}")
        return None

    def resolve_font(self, requested_family: str, bold: bool = False, italic: bool = False) -> FontRegistryEntry:
        """
        Resolves requested font family and style deterministically.
        Supports resolution by family name, PostScript name, stable ID, full name, filename stem,
        or clean phonetic spelling variants (e.g. TF PHETAI -> TF Phethai).
        """
        if bold and italic:
            requested_style = "bold_italic"
        elif bold:
            requested_style = "bold"
        elif italic:
            requested_style = "italic"
        else:
            requested_style = "regular"

        req_norm = (requested_family or "").lower().strip()
        req_clean = self._clean_font_key(req_norm)
        
        # 1. Direct and Clean Alias match
        alias_match = (
            self.aliases.get(req_norm)
            or self._clean_aliases.get(req_clean)
            or (self._clean_aliases.get(req_clean[2:]) if req_clean.startswith("th") and len(req_clean) > 3 else None)
            or self._clean_aliases.get(f"th{req_clean}")
        )

        # 2. Suffix-stripped query match (e.g. "Baijam Bold" -> "Baijam")
        if not alias_match:
            for suffix in ["regular", "bold", "medium", "demo", "v1", "v10"]:
                if req_clean.endswith(suffix) and len(req_clean) > len(suffix) + 2:
                    sub_key = req_clean[:-len(suffix)]
                    alias_match = (
                        self._clean_aliases.get(sub_key)
                        or (self._clean_aliases.get(sub_key[2:]) if sub_key.startswith("th") and len(sub_key) > 3 else None)
                        or self._clean_aliases.get(f"th{sub_key}")
                    )
                    if alias_match:
                        break

        if alias_match:
            resolved_family, resolved_style = alias_match
            if req_norm == resolved_family.lower().strip() or req_clean == self._clean_font_key(resolved_family):
                target_style = requested_style
            else:
                target_style = resolved_style if resolved_style != "regular" else requested_style
            
            lookup_key = f"{resolved_family.lower()}_{target_style}"
            entry = self.registry.get(lookup_key)
            if entry:
                return replace(entry, is_fallback=False)

            # Style fallback within resolved family
            fallback_styles = []
            if target_style == "bold_italic":
                fallback_styles = ["bold", "italic", "regular"]
            elif target_style == "bold":
                fallback_styles = ["regular", "bold_italic", "italic"]
            elif target_style == "italic":
                fallback_styles = ["regular", "bold_italic", "bold"]
            else:
                fallback_styles = ["bold", "italic", "bold_italic"]

            for fb_style in fallback_styles:
                fallback_style_key = f"{resolved_family.lower()}_{fb_style}"
                entry = self.registry.get(fallback_style_key)
                if entry:
                    is_fb = (entry.style != requested_style) if requested_style != "regular" else False
                    return replace(entry, is_fallback=is_fb)

        # 3. Direct variant match by PostScript or variant ID
        if req_norm in self.variants_by_id:
            entry = self.variants_by_id[req_norm]
            is_fb = (entry.style != requested_style) if requested_style != "regular" else False
            return replace(entry, is_fallback=is_fb)

        # 4. Family fallback: map standard aliases
        family_map = {
            "notosansthai": "Tahoma",
            "noto sans thai": "Tahoma",
            "arialmt": "Arial",
            "fc sukhumvit": "Tahoma",
            "prompt": "Tahoma",
            "sarabun": "Tahoma"
        }
        fallback_family = family_map.get(req_norm, "Tahoma")
        fallback_key = f"{fallback_family.lower()}_{requested_style}"
        fallback_entry = self.registry.get(fallback_key) or self.registry.get(f"{fallback_family.lower()}_regular")

        if not fallback_entry:
            if self.registry:
                fallback_entry = list(self.registry.values())[0]
            else:
                raise RuntimeError("No system fonts are registered in FontRegistry.")

        warn_key = f"{requested_family}_{requested_style}".lower()
        if warn_key not in self._warned_fonts:
            self._warned_fonts.add(warn_key)
            is_prod = os.environ.get("PRODUCTION_MODE", "0") == "1"
            msg = f"Font '{requested_family}' (style: {requested_style}) not found. Falling back to '{fallback_entry.family}' ({fallback_entry.style})."
            if is_prod:
                logger.warning(f"[PREFLIGHT WARNING] {msg}")
            else:
                logger.warning(msg)
        
        return replace(fallback_entry, is_fallback=True)

# Global font registry instance
font_registry = FontRegistry()

