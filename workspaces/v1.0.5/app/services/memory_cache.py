"""In-memory cache for page images, patch crops, and composite clean frames.

Reduces disk I/O and speeds up interactive block recleaning & image serving.
Inspired by ImageTrans's in-memory matrix and patch-compositing architecture.
"""

from dataclasses import dataclass, field
import time
from typing import Dict, Optional, Tuple
import numpy as np


@dataclass
class PatchEntry:
    patch: np.ndarray  # Inpainted crop image (BGR)
    bounds: Tuple[int, int, int, int]  # (x0, y0, x1, y1)
    fingerprint: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class PageCacheEntry:
    page_id: str
    source_image: Optional[np.ndarray] = None
    clean_composite: Optional[np.ndarray] = None
    patches: Dict[str, PatchEntry] = field(default_factory=dict)  # block_id -> PatchEntry
    is_dirty: bool = False
    last_accessed: float = field(default_factory=time.time)


class PageImageCacheManager:
    """Singleton memory cache manager with LRU eviction and memory budget enforcement."""

    def __init__(self, max_memory_mb: float = 1000.0):
        self._cache: Dict[str, PageCacheEntry] = {}
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024)

    def get_entry(self, page_id: str) -> PageCacheEntry:
        if page_id not in self._cache:
            self._cache[page_id] = PageCacheEntry(page_id=page_id)
        entry = self._cache[page_id]
        entry.last_accessed = time.time()
        return entry

    def get_source_image(self, page_id: str) -> Optional[np.ndarray]:
        if page_id in self._cache:
            entry = self._cache[page_id]
            entry.last_accessed = time.time()
            return entry.source_image
        return None

    def set_source_image(self, page_id: str, image: np.ndarray) -> None:
        entry = self.get_entry(page_id)
        entry.source_image = image.copy()
        self._evict_if_needed()

    def get_clean_composite(self, page_id: str) -> Optional[np.ndarray]:
        if page_id in self._cache:
            entry = self._cache[page_id]
            entry.last_accessed = time.time()
            return entry.clean_composite
        return None

    def set_clean_composite(self, page_id: str, image: np.ndarray, is_dirty: bool = False) -> None:
        entry = self.get_entry(page_id)
        entry.clean_composite = image.copy()
        entry.is_dirty = is_dirty
        self._evict_if_needed()

    def get_patch(self, page_id: str, block_id: str) -> Optional[PatchEntry]:
        if page_id in self._cache:
            entry = self._cache[page_id]
            entry.last_accessed = time.time()
            return entry.patches.get(block_id)
        return None

    def set_patch(
        self,
        page_id: str,
        block_id: str,
        patch: np.ndarray,
        bounds: Tuple[int, int, int, int],
        fingerprint: str,
        is_dirty: bool = True,
    ) -> None:
        entry = self.get_entry(page_id)
        entry.patches[block_id] = PatchEntry(
            patch=patch.copy(),
            bounds=bounds,
            fingerprint=fingerprint,
            timestamp=time.time(),
        )
        entry.is_dirty = is_dirty
        self._evict_if_needed()

    def invalidate_block(self, page_id: str, block_id: str) -> None:
        if page_id in self._cache:
            entry = self._cache[page_id]
            entry.patches.pop(block_id, None)
            entry.clean_composite = None
            entry.is_dirty = True

    def invalidate_page(self, page_id: str) -> None:
        self._cache.pop(page_id, None)

    def clear(self) -> None:
        self._cache.clear()

    def estimate_memory_bytes(self) -> int:
        total = 0
        for entry in self._cache.values():
            if entry.source_image is not None:
                total += entry.source_image.nbytes
            if entry.clean_composite is not None:
                total += entry.clean_composite.nbytes
            for patch_entry in entry.patches.values():
                total += patch_entry.patch.nbytes
        return total

    def _evict_if_needed(self) -> None:
        current_mem = self.estimate_memory_bytes()
        if current_mem <= self.max_memory_bytes:
            return

        # Sort pages by last_accessed ascending (LRU)
        sorted_pages = sorted(self._cache.items(), key=lambda item: item[1].last_accessed)
        
        # Pass 1: Evict clean / persisted pages
        for page_id, entry in sorted_pages:
            if not entry.is_dirty:
                self._cache.pop(page_id, None)
                if self.estimate_memory_bytes() <= self.max_memory_bytes:
                    return

        # Pass 2: If memory still exceeded, free high-memory source images from older pages
        for page_id, entry in sorted_pages:
            if entry.source_image is not None:
                entry.source_image = None
                if self.estimate_memory_bytes() <= self.max_memory_bytes:
                    return

        # Pass 3: Hard memory budget enforcement - evict oldest pages completely
        for page_id, entry in sorted_pages:
            self._cache.pop(page_id, None)
            if self.estimate_memory_bytes() <= self.max_memory_bytes:
                return


# Global singleton instance
page_image_cache = PageImageCacheManager()
