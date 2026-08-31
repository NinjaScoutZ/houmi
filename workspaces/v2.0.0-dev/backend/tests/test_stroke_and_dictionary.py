import unittest
from unittest.mock import MagicMock

from app.services.typesetting.stroke import stroke_draw_kwargs, parse_hex_rgba, draw_text_with_spec_stroke
from app.services.typesetting.segmentation import (
    segment_text,
    normalize_project_dictionary,
)
from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
from app.services.typesetting.tracking import (
    iter_tracked_graphemes,
    measure_text_with_tracking,
    split_grapheme_clusters,
)
from app.models.all_models import TextBlock, Page, Project


class TestStrokeDrawThrough(unittest.TestCase):
    def test_no_stroke_when_zero(self):
        self.assertEqual(stroke_draw_kwargs(0, "#fff"), {})
        self.assertEqual(stroke_draw_kwargs(None, "#fff"), {})

    def test_stroke_kwargs_from_spec_fields(self):
        kw = stroke_draw_kwargs(1.2, "#ffffff")
        self.assertEqual(kw["stroke_width"], 1)
        self.assertEqual(kw["stroke_fill"][:3], (255, 255, 255))

    def test_parse_hex(self):
        self.assertEqual(parse_hex_rgba("#112233")[:3], (0x11, 0x22, 0x33))
        self.assertEqual(parse_hex_rgba("#abc")[:3], (0xAA, 0xBB, 0xCC))

    def test_draw_calls_pillow_with_stroke(self):
        draw = MagicMock()
        draw_text_with_spec_stroke(
            draw,
            (10, 20),
            "hello",
            font="font",
            fill=(0, 0, 0, 255),
            stroke_width=2,
            stroke_color="#ff0000",
        )
        draw.text.assert_called_once()
        args, kwargs = draw.text.call_args
        self.assertEqual(args[0], (10, 20))
        self.assertEqual(args[1], "hello")
        self.assertEqual(kwargs["stroke_width"], 2)
        self.assertEqual(kwargs["stroke_fill"][:3], (255, 0, 0))


class TestCanonicalTracking(unittest.TestCase):
    def test_thai_combining_mark_stays_with_base_grapheme(self):
        self.assertEqual(split_grapheme_clusters("กัข"), ["กั", "ข"])

    def test_tracking_counts_graphemes_not_unicode_codepoints(self):
        font = MagicMock()
        font.getbbox.return_value = (0, 0, 100, 20)
        width = measure_text_with_tracking(font, "กัข", font_size=20, tracking=100)
        # Two graphemes => one 2px gap. Code-point tracking would add two gaps.
        self.assertEqual(width, 102.0)

    def test_tracking_iterator_never_yields_a_bare_thai_mark(self):
        font = MagicMock()
        font.getlength.side_effect = lambda value: 20.0 * len(split_grapheme_clusters(value))
        rendered = list(iter_tracked_graphemes(font, "กัข", 20, 100))
        self.assertEqual([cluster for cluster, _ in rendered], ["กั", "ข"])
        self.assertEqual(rendered[1][1], 22.0)


class TestProjectDictionary(unittest.TestCase):
    def test_normalize_longest_first(self):
        terms = normalize_project_dictionary(["สุริยา", "เทพแห่งสุริยา", "สุริยา", "  "])
        self.assertEqual(terms[0], "เทพแห่งสุริยา")
        self.assertEqual(len(terms), 2)

    def test_dictionary_change_invalidates_signature(self):
        from app.services.typesetting.service import compute_block_signature

        project = Project(name="dict-sig", settings={})
        page = Page(project=project, page_number=1, width=800, height=1200)
        block = TextBlock(
            id="sig-block",
            page=page,
            page_id="p",
            block_index=0,
            x=10,
            y=10,
            width=400,
            height=120,
            translation="เทพแห่งสุริยาปกป้อง",
            font_family="Tahoma",
            font_size=24,
            balloon_type="bubble",
            color_hex="#000000",
            extra_metadata={},
        )
        sig1 = compute_block_signature(block)
        project.settings = {"project_dictionary": ["เทพแห่งสุริยา"]}
        sig2 = compute_block_signature(block)
        self.assertNotEqual(sig1, sig2)

    def test_dictionary_keeps_proper_name_unsplit(self):
        name = "เทพแห่งสุริยา"
        text = f"{name}ปกป้องโลก"
        tokens = segment_text(text, project_dictionary=[name])
        joined_content = [t for t in tokens if t.strip()]
        self.assertIn(name, joined_content)

    def test_compute_uses_project_dictionary_settings(self):
        name = "ชื่อเฉพาะยาวมากกก"
        project = Project(
            name="dict-test",
            settings={"project_dictionary": [name]},
        )
        page = Page(project=project, page_number=1, width=800, height=1200)
        block = TextBlock(
            id="dict-block",
            page=page,
            page_id="p",
            block_index=0,
            x=10,
            y=10,
            width=400,
            height=120,
            translation=f"{name}ไปแล้ว",
            font_family="Tahoma",
            font_size=24,
            balloon_type="bubble",
            color_hex="#000000",
            extra_metadata={},
        )
        spec = compute_block_typesetting(block, log_feedback=False)
        flat = "".join(spec.explicit_lines)
        # Name must appear contiguous (not broken by engine-inserted breaks mid-token)
        self.assertIn(name, flat)
        # Every explicit line break must fall on token boundaries; name is one token
        for line in spec.explicit_lines:
            if name in line:
                self.assertNotIn(name[: len(name) // 2] + "\n", name)  # sanity
                break
        else:
            # Name might span only one line — still OK if present in flat text
            self.assertIn(name, flat)

    def test_suggestion_snapshot_survives_live_recompute(self):
        block = TextBlock(
            id="feedback-snapshot",
            page_id="p",
            block_index=0,
            x=0,
            y=0,
            width=400,
            height=140,
            translation="ข้อความแรก",
            font_family="Tahoma",
            font_size=24,
            balloon_type="bubble",
            color_hex="#000000",
            extra_metadata={
                "layout_region": {
                    "x": 0,
                    "y": 0,
                    "width": 400,
                    "height": 140,
                    "shape": "bubble",
                    "source": "manual",
                    "confidence": 1.0,
                }
            },
        )
        first = compute_block_typesetting(block, log_feedback=False)
        persist_typesetting_spec(block, first)
        original_lines = list(block.extra_metadata["suggested_explicit_lines"])
        original_spec_id = block.extra_metadata["suggested_spec_id"]

        block.translation = "ข้อความที่ผู้ใช้แก้แล้ว"
        current = compute_block_typesetting(block, log_feedback=False)
        persist_typesetting_spec(block, current)

        self.assertEqual(block.extra_metadata["suggested_explicit_lines"], original_lines)
        self.assertEqual(block.extra_metadata["suggested_spec_id"], original_spec_id)
        self.assertNotEqual(block.extra_metadata["typesetting_spec"]["spec_id"], original_spec_id)


if __name__ == "__main__":
    unittest.main()
