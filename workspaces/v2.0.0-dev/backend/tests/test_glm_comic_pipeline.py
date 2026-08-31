"""
Test Suite for GLM Comic Pipeline - Batch Grid Packing and Grounded Parsing.
"""
import os
import sys
import unittest
import numpy as np
import cv2

# Add backend to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from ocr_server.glm_comic_pipeline import GLMComicPipeline

class TestGLMComicPipeline(unittest.TestCase):
    def setUp(self):
        # Create 6 synthetic balloon images
        self.test_images = []
        for i in range(6):
            img = np.full((180, 220, 3), 240, dtype=np.uint8)
            cv2.putText(img, f"Text {i+1}", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 180), 2)
            self.test_images.append(img)

    def test_grid_packing(self):
        """Test packing 6 images into a 3x3 grid collage."""
        canvas, metadata = GLMComicPipeline.pack_grid(self.test_images, grid_size=3, cell_size=300)
        self.assertEqual(canvas.shape, (900, 900, 3))
        self.assertEqual(len(metadata), 6)
        self.assertEqual(metadata[0]["grid_coord"], (0, 0))
        self.assertEqual(metadata[5]["grid_coord"], (1, 2))

    def test_grounded_box_parser(self):
        """Test parsing normalized coordinate bounding boxes."""
        sample_output = "Title: [100, 200, 400, 800] Sample Text Inside Balloon\n(500, 100, 700, 600) Second Line"
        boxes = GLMComicPipeline.parse_grounded_boxes(sample_output, (1000, 1000))
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0]["normalized"], [100, 200, 400, 800])
        self.assertEqual(boxes[0]["text"], "Sample Text Inside Balloon")
        self.assertEqual(boxes[1]["normalized"], [500, 100, 700, 600])
        self.assertEqual(boxes[1]["text"], "Second Line")

if __name__ == "__main__":
    unittest.main()