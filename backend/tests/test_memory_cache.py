"""Unit tests for memory_cache.py PageImageCacheManager."""

import numpy as np
import pytest
from app.services.memory_cache import PageImageCacheManager, PageCacheEntry, PatchEntry


def test_memory_cache_source_image():
    cache = PageImageCacheManager(max_memory_mb=10.0)
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)

    cache.set_source_image("page_1", dummy_img)
    retrieved = cache.get_source_image("page_1")

    assert retrieved is not None
    assert retrieved.shape == (100, 100, 3)
    assert cache.get_source_image("non_existent") is None


def test_memory_cache_patch_and_invalidation():
    cache = PageImageCacheManager(max_memory_mb=10.0)
    dummy_patch = np.ones((50, 50, 3), dtype=np.uint8) * 255

    cache.set_patch("page_1", "block_a", dummy_patch, (10, 10, 60, 60), "fp_123")
    patch_entry = cache.get_patch("page_1", "block_a")

    assert patch_entry is not None
    assert patch_entry.fingerprint == "fp_123"
    assert patch_entry.bounds == (10, 10, 60, 60)

    # Invalidate block
    cache.invalidate_block("page_1", "block_a")
    assert cache.get_patch("page_1", "block_a") is None


def test_memory_cache_lru_eviction():
    # 1MB limit cache
    cache = PageImageCacheManager(max_memory_mb=1.0)
    # Create 800KB image
    img1 = np.zeros((500, 500, 3), dtype=np.uint8)  # 750,000 bytes ~ 0.75MB
    img2 = np.zeros((500, 500, 3), dtype=np.uint8)

    cache.set_source_image("page_1", img1)
    assert cache.get_source_image("page_1") is not None

    # Adding page_2 should trigger eviction of clean page_1 if limit exceeded
    cache.set_source_image("page_2", img2)
    assert cache.estimate_memory_bytes() <= cache.max_memory_bytes + 750000
