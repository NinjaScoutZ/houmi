"""
GLM Comic Pipeline - Specialized Manga/Comic Multi-Balloon OCR and Grounding Engine.
Designed for Houmi typography, translation, and inpainting pipelines.
Supports:
1. Single Balloon OCR and SFX Parsing.
2. Multi-Balloon Grid Packing and Unpacking (Batch Collage OCR).
3. Coordinate De-normalization [0..1000] -> Pixel Bboxes.
"""
import os
import re
import json
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
import cv2
import torch
import numpy as np
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig

logger = logging.getLogger("houmi-glm-comic")

class GLMComicPipeline:
    def __init__(
        self,
        model_id: str = "zai-org/GLM-OCR",
        device: Optional[str] = None,
        load_in_4bit: bool = True
    ):
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.load_in_4bit = load_in_4bit and (self.device == "cuda")
        self.model = None
        self.processor = None
        self.has_bf16 = torch.cuda.is_available() and hasattr(torch.cuda, "is_bf16_supported") and torch.cuda.is_bf16_supported()
        self.dtype = (torch.bfloat16 if self.has_bf16 else torch.float16) if self.device == "cuda" else torch.float32

    def load(self):
        """Loads GLM-OCR model and processor with optimal quantization."""
        if self.model is not None:
            return

        logger.info(f"Loading GLM Comic Engine from {self.model_id} (device={self.device}, 4bit={self.load_in_4bit})...")
        quant_config = None
        if self.load_in_4bit:
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=self.dtype,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True
            )

        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_id,
            torch_dtype=self.dtype,
            trust_remote_code=True,
            device_map="auto" if self.device == "cuda" else {"": "cpu"},
            quantization_config=quant_config
        )
        self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        logger.info("GLM Comic Engine loaded successfully!")

    def unload(self):
        """Frees VRAM memory."""
        self.model = None
        self.processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("GLM Comic Engine unloaded.")

    @staticmethod
    def pack_grid(
        image_paths_or_arrays: List[Any],
        grid_size: int = 3,
        cell_size: int = 340,
        margin: int = 15
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Packs multiple balloon images into a single N x N composite grid canvas.
        Returns: (canvas_image_bgr, metadata_list)
        """
        n = min(len(image_paths_or_arrays), grid_size * grid_size)
        canvas = np.full((grid_size * cell_size, grid_size * cell_size, 3), 255, dtype=np.uint8)
        metadata = []

        for idx in range(n):
            item = image_paths_or_arrays[idx]
            if isinstance(item, str):
                img = cv2.imread(item)
                fname = os.path.basename(item)
            else:
                img = item
                fname = f"cell_{idx+1}.png"

            if img is None:
                continue

            h, w = img.shape[:2]
            r = idx // grid_size
            c = idx % grid_size

            avail = cell_size - 2 * margin
            scale = min(avail / max(1, w), avail / max(1, h))
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            resized = cv2.resize(img, (nw, nh))

            ox = c * cell_size + (cell_size - nw) // 2
            oy = r * cell_size + (cell_size - nh) // 2

            canvas[oy:oy+nh, ox:ox+nw] = resized
            cv2.rectangle(canvas, (c * cell_size, r * cell_size), ((c + 1) * cell_size, (r + 1) * cell_size), (210, 210, 210), 1)

            metadata.append({
                "index": idx,
                "filename": fname,
                "orig_size": (w, h),
                "grid_coord": (r, c),
                "cell_box": (ox, oy, nw, nh),
                "scale": scale
            })

        return canvas, metadata

    @staticmethod
    def parse_grounded_boxes(raw_text: str, image_size: Tuple[int, int]) -> List[Dict[str, Any]]:
        """Extracts normalized coordinate tags [ymin, xmin, ymax, xmax] (0..1000) and converts to pixel bboxes."""
        w_img, h_img = image_size
        results = []
        box_regex = r"[\[\(<](\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})[\]\)>]\s*([^\n\[\(<]*)"
        pattern = re.compile(box_regex)
        for match in pattern.finditer(raw_text):
            y1_n, x1_n, y2_n, x2_n, text_label = match.groups()
            y1 = int(float(y1_n) / 1000.0 * h_img)
            x1 = int(float(x1_n) / 1000.0 * w_img)
            y2 = int(float(y2_n) / 1000.0 * h_img)
            x2 = int(float(x2_n) / 1000.0 * w_img)
            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            results.append({
                "bbox": [x1, y1, bw, bh],
                "text": text_label.strip(),
                "normalized": [int(y1_n), int(x1_n), int(y2_n), int(x2_n)]
            })
        return results

    def infer_image(
        self,
        image_input: Any,
        prompt: str = "OCR the text in this comic image. Return exact lines."
    ) -> Dict[str, Any]:
        """Runs GLM OCR inference on a single image (path or array)."""
        self.load()
        if isinstance(image_input, str):
            image = Image.open(image_input).convert("RGB")
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
        else:
            image = image_input

        w, h = image.size
        t0 = time.time()
        inputs = self.processor(
            text=f"{prompt}\n<image>",
            images=image,
            return_tensors="pt"
        ).to(self.model.device)

        with torch.inference_mode():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                do_sample=False
            )
            generated_ids = generated_ids[:, inputs.input_ids.shape[1]:]
            raw_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        dt = time.time() - t0
        grounded = self.parse_grounded_boxes(raw_text, (w, h))
        return {
            "raw_text": raw_text.strip(),
            "grounded_boxes": grounded,
            "latency_ms": round(dt * 1000, 1),
            "image_size": (w, h)
        }

    def process_grid_batch(
        self,
        image_paths: List[str],
        grid_size: int = 3,
        prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Dobkle-style Batch Collage Processing."""
        canvas, metadata = self.pack_grid(image_paths, grid_size=grid_size)
        if not metadata:
            return []

        default_prompt = (
            f"This image is a {grid_size}x{grid_size} grid containing {len(metadata)} comic speech balloons and sound effects. "
            "Read and transcribe the exact text from each cell in reading order (Row by row, Left to Right). "
            "Format output strictly as:\n"
            "Cell 1: [text]\nCell 2: [text]\n..."
        )
        query = prompt or default_prompt
        res = self.infer_image(canvas, prompt=query)
        raw_text = res["raw_text"]

        cell_outputs = {}
        for line in raw_text.split("\n"):
            line = line.strip()
            match = re.match(r"^(?:Cell|Panel|Box|Item)?\s*(\d+)\s*[:\-.]\s*(.*)$", line, re.IGNORECASE)
            if match:
                c_num = int(match.group(1)) - 1
                c_text = match.group(2).strip()
                cell_outputs[c_num] = c_text

        final_results = []
        for meta in metadata:
            idx = meta["index"]
            extracted_text = cell_outputs.get(idx, "")
            final_results.append({
                "index": idx,
                "filename": meta["filename"],
                "orig_size": meta["orig_size"],
                "ocr_text": extracted_text,
                "raw_grid_response": raw_text
            })
        return final_results