# Async OCR Implementation
# backend/app/services/ocr_async.py

"""
Asynchronous OCR implementation for parallel processing of multiple text blocks.
Uses httpx + asyncio for concurrent API requests.
"""

import asyncio
import logging
import base64
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
import httpx
from PIL import Image
import io

logger = logging.getLogger("houmi-ocr-async")


class AsyncOCRService:
    """Asynchronous OCR service for parallel text recognition."""

    def __init__(self, api_url: str, timeout: float = 30.0):
        self.api_url = api_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ocr_single_block(
        self,
        image_path: str,
        block_coords: Tuple[int, int, int, int],
        source_lang: str = "ja",
    ) -> Tuple[str, bool]:
        """
        OCR a single text block.

        Args:
            image_path: Path to source image
            block_coords: (x, y, width, height) tuple
            source_lang: Source language code

        Returns:
            Tuple of (recognized_text, success)
        """
        if not self._client:
            raise RuntimeError("AsyncOCRService not initialized. Use 'async with' context.")

        try:
            # Extract crop
            crop = self._extract_crop(image_path, block_coords)
            if crop is None:
                return ("", False)

            # Encode to base64
            base64_img = self._encode_image_base64(crop)

            # Call API
            response = await self._client.post(
                self.api_url,
                json={
                    "image": base64_img,
                    "source_lang": source_lang,
                },
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "")
                return (text, True)
            else:
                logger.warning(f"OCR API returned status {response.status_code}")
                return ("", False)

        except asyncio.TimeoutError:
            logger.error(f"OCR timeout for block at {block_coords}")
            return ("", False)
        except Exception as e:
            logger.error(f"OCR failed for block at {block_coords}: {e}")
            return ("", False)

    async def ocr_blocks_parallel(
        self,
        image_path: str,
        blocks: List[dict],
        max_concurrent: int = 5,
        source_lang: str = "ja",
    ) -> List[Tuple[str, bool]]:
        """
        OCR multiple blocks in parallel.

        Args:
            image_path: Path to source image
            blocks: List of block dicts with x, y, width, height
            max_concurrent: Max concurrent requests (default 5)
            source_lang: Source language code

        Returns:
            List of (text, success) tuples in same order as blocks
        """
        total = len(blocks)
        logger.info(f"Starting parallel OCR for {total} blocks (max_concurrent={max_concurrent})")

        # Create tasks
        tasks = []
        for block in blocks:
            coords = (
                int(block.get("x", 0)),
                int(block.get("y", 0)),
                int(block.get("width", 0)),
                int(block.get("height", 0)),
            )
            task = self.ocr_single_block(image_path, coords, source_lang)
            tasks.append(task)

        # Process in batches to limit concurrent requests
        results = []
        for i in range(0, total, max_concurrent):
            batch = tasks[i:i + max_concurrent]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            # Handle exceptions
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Batch OCR error for block {i + idx}: {result}")
                    results.append(("", False))
                else:
                    results.append(result)

            if (i + max_concurrent) < total:
                logger.info(f"Completed {min(i + max_concurrent, total)}/{total} blocks")

        logger.info(f"Parallel OCR completed: {total} blocks")
        return results

    def _extract_crop(
        self,
        image_path: str,
        coords: Tuple[int, int, int, int],
    ) -> Optional[Image.Image]:
        """Extract crop from image."""
        try:
            x, y, width, height = coords
            with Image.open(image_path) as img:
                crop = img.crop((x, y, x + width, y + height))
                return crop.copy()
        except Exception as e:
            logger.error(f"Failed to extract crop: {e}")
            return None

    def _encode_image_base64(self, img: Image.Image) -> str:
        """Encode PIL Image to base64 string."""
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        return base64.b64encode(img_bytes).decode("utf-8")


# Cache for OCR results
class OCRCache:
    """Simple in-memory cache for OCR results."""

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, str] = {}
        self._max_size = max_size

    def get_cache_key(self, image_path: str, coords: Tuple[int, int, int, int]) -> str:
        """Generate cache key from image path and coordinates."""
        data = f"{image_path}_{coords[0]}_{coords[1]}_{coords[2]}_{coords[3]}"
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, key: str) -> Optional[str]:
        """Get cached result."""
        return self._cache.get(key)

    def set(self, key: str, value: str):
        """Set cached result."""
        if len(self._cache) >= self._max_size:
            # Simple eviction: remove oldest (first inserted)
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value

    def clear(self):
        """Clear all cached results."""
        self._cache.clear()


# Global cache instance
_ocr_cache = OCRCache()


async def ocr_blocks_with_cache(
    image_path: str,
    blocks: List[dict],
    api_url: str,
    max_concurrent: int = 5,
    source_lang: str = "ja",
    use_cache: bool = True,
) -> List[str]:
    """
    OCR multiple blocks with caching support.

    Args:
        image_path: Path to source image
        blocks: List of block dicts
        api_url: OCR API URL
        max_concurrent: Max concurrent requests
        source_lang: Source language code
        use_cache: Whether to use cache

    Returns:
        List of recognized texts
    """
    results = []
    blocks_to_process = []
    cache_keys = []

    # Check cache first
    for block in blocks:
        coords = (
            int(block.get("x", 0)),
            int(block.get("y", 0)),
            int(block.get("width", 0)),
            int(block.get("height", 0)),
        )
        cache_key = _ocr_cache.get_cache_key(image_path, coords)
        cache_keys.append(cache_key)

        if use_cache:
            cached = _ocr_cache.get(cache_key)
            if cached is not None:
                logger.info(f"Using cached OCR result for block at {coords}")
                results.append(cached)
                continue

        # Need to process this block
        blocks_to_process.append((block, cache_key, len(results)))
        results.append(None)  # Placeholder

    # Process uncached blocks
    if blocks_to_process:
        logger.info(f"Processing {len(blocks_to_process)} uncached blocks")

        async with AsyncOCRService(api_url) as ocr_service:
            uncached_blocks = [item[0] for item in blocks_to_process]
            ocr_results = await ocr_service.ocr_blocks_parallel(
                image_path,
                uncached_blocks,
                max_concurrent,
                source_lang,
            )

            # Update results and cache
            for (block, cache_key, idx), (text, success) in zip(blocks_to_process, ocr_results):
                results[idx] = text
                if use_cache and success and text:
                    _ocr_cache.set(cache_key, text)

    return results


# Synchronous wrapper for backward compatibility
def ocr_blocks_parallel_sync(
    image_path: str,
    blocks: List[dict],
    api_url: str,
    max_concurrent: int = 5,
    source_lang: str = "ja",
    use_cache: bool = True,
) -> List[str]:
    """
    Synchronous wrapper for async OCR.

    Args:
        image_path: Path to source image
        blocks: List of block dicts
        api_url: OCR API URL
        max_concurrent: Max concurrent requests
        source_lang: Source language code
        use_cache: Whether to use cache

    Returns:
        List of recognized texts
    """
    coro = ocr_blocks_with_cache(
        image_path,
        blocks,
        api_url,
        max_concurrent,
        source_lang,
        use_cache,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)
