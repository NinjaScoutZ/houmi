import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routes.blocks import _apply_block_update
from app.schemas.all_schemas import TextBlockUpdate


class BlockGeometryContractTests(unittest.TestCase):
    @patch("app.services.typesetting.persist_typesetting_spec")
    @patch("app.services.typesetting.compute_block_typesetting")
    def test_geometry_update_synchronizes_text_bbox_metadata(self, compute, persist):
        compute.return_value = SimpleNamespace()
        block = SimpleNamespace(
            x=10.0,
            y=20.0,
            width=100.0,
            height=50.0,
            extra_metadata={
                "text_bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                "layout_region": {"x": 0, "y": 0, "width": 200, "height": 100},
            },
            page=None,
        )

        _apply_block_update(
            block,
            TextBlockUpdate(x=30, y=40, width=180, height=90),
        )

        self.assertEqual(
            block.extra_metadata["text_bbox"],
            {"x": 30.0, "y": 40.0, "width": 180.0, "height": 90.0},
        )
        self.assertEqual(
            block.extra_metadata["layout_region"],
            {"x": 0, "y": 0, "width": 200, "height": 100},
        )


if __name__ == "__main__":
    unittest.main()
