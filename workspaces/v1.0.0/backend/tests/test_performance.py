import unittest

from app.services.performance import resolve_performance_settings
from app.services.performance_presets import (
    list_presets,
    get_preset,
    apply_preset_to_settings,
    get_active_preset_name,
)
from app.services.parallel_inpaint import get_optimal_worker_count
from app.services.ocr_async import OCRCache


class TestPerformanceSettings(unittest.TestCase):
    def test_balanced_is_the_safe_default(self):
        settings = resolve_performance_settings(None)
        self.assertEqual(settings.profile, "balanced")
        self.assertEqual(settings.ocr_workers, 2)

    def test_custom_values_are_bounded(self):
        settings = resolve_performance_settings({
            "performance_profile": "custom",
            "performance_custom": {
                "preview_width": 99999,
                "typesetting_candidates": 2,
                "ocr_workers": 20,
                "prefer_gpu": False,
            },
        })
        self.assertEqual(settings.preview_width, 2400)
        self.assertEqual(settings.typesetting_candidates, 12)
        self.assertEqual(settings.ocr_workers, 4)
        self.assertFalse(settings.prefer_gpu)


class TestPerformancePresets(unittest.TestCase):
    """Test performance preset system."""

    def test_list_presets(self):
        """Test that all presets are listed."""
        presets = list_presets()
        self.assertEqual(len(presets), 3)
        self.assertTrue(any(p["id"] == "ultra_fast" for p in presets))
        self.assertTrue(any(p["id"] == "balanced" for p in presets))
        self.assertTrue(any(p["id"] == "high_quality" for p in presets))

    def test_get_preset_ultra_fast(self):
        """Test ultra_fast preset configuration."""
        preset = get_preset("ultra_fast")
        self.assertEqual(preset["inpaint_engine"], "telea")
        self.assertEqual(preset["mask_gen_method"], "rectangle")
        self.assertEqual(preset["parallel_inpaint_workers"], 0)  # Auto-detect
        self.assertEqual(preset["preview_width"], 1200)

    def test_get_preset_balanced(self):
        """Test balanced preset configuration."""
        preset = get_preset("balanced")
        self.assertEqual(preset["inpaint_engine"], "lama")
        self.assertEqual(preset["mask_gen_method"], "hybrid")
        self.assertEqual(preset["parallel_inpaint_workers"], 0)  # Auto-detect
        self.assertEqual(preset["preview_width"], 1600)

    def test_get_preset_high_quality(self):
        """Test high_quality preset configuration."""
        preset = get_preset("high_quality")
        self.assertEqual(preset["inpaint_engine"], "mat")
        self.assertEqual(preset["parallel_inpaint_workers"], 0)  # Auto-detect
        self.assertEqual(preset["preview_width"], 2400)

    def test_apply_preset_to_settings(self):
        """Test applying preset to settings."""
        base_settings = {"some_key": "some_value"}
        updated = apply_preset_to_settings(base_settings, "ultra_fast")

        self.assertEqual(updated["inpaint_engine"], "telea")
        self.assertEqual(updated["parallel_inpaint_workers"], 0)  # Auto-detect
        self.assertEqual(updated["active_performance_preset"], "ultra_fast")
        self.assertEqual(updated["some_key"], "some_value")  # Original preserved

    def test_get_active_preset_name(self):
        """Test getting active preset name."""
        settings = {"active_performance_preset": "ultra_fast"}
        self.assertEqual(get_active_preset_name(settings), "ultra_fast")

        # Test default
        self.assertEqual(get_active_preset_name({}), "balanced")


class TestParallelInpaint(unittest.TestCase):
    """Test parallel inpainting utilities."""

    def test_get_optimal_worker_count_auto(self):
        """Test auto-detection of worker count."""
        workers = get_optimal_worker_count({})
        self.assertGreaterEqual(workers, 2)
        self.assertLessEqual(workers, 8)

    def test_get_optimal_worker_count_configured(self):
        """Test configured worker count."""
        settings = {"parallel_inpaint_workers": 5}
        workers = get_optimal_worker_count(settings)
        self.assertEqual(workers, 5)

    def test_get_optimal_worker_count_cap(self):
        """Test worker count is capped at 8."""
        settings = {"parallel_inpaint_workers": 100}
        workers = get_optimal_worker_count(settings)
        self.assertEqual(workers, 8)

    def test_get_optimal_worker_count_minimum(self):
        """Test worker count minimum of 2."""
        settings = {"parallel_inpaint_workers": 0}
        workers = get_optimal_worker_count(settings)
        self.assertGreaterEqual(workers, 2)


class TestOCRAsync(unittest.TestCase):
    """Test async OCR utilities."""

    def test_ocr_cache_key_generation(self):
        """Test OCR cache key generation."""
        cache = OCRCache()
        key1 = cache.get_cache_key("test.png", (0, 0, 100, 50))
        key2 = cache.get_cache_key("test.png", (0, 0, 100, 50))
        key3 = cache.get_cache_key("test.png", (0, 0, 100, 51))

        self.assertEqual(key1, key2)  # Same input = same key
        self.assertNotEqual(key1, key3)  # Different coords = different key

    def test_ocr_cache_get_set(self):
        """Test OCR cache get/set."""
        cache = OCRCache()
        cache.set("test_key", "test_value")
        self.assertEqual(cache.get("test_key"), "test_value")
        self.assertIsNone(cache.get("unknown_key"))

    def test_ocr_cache_eviction(self):
        """Test OCR cache eviction when full."""
        cache = OCRCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        self.assertIsNone(cache.get("key1"))  # Evicted
        self.assertEqual(cache.get("key2"), "value2")
        self.assertEqual(cache.get("key3"), "value3")
        self.assertEqual(cache.get("key4"), "value4")

    def test_ocr_cache_clear(self):
        """Test OCR cache clear."""
        cache = OCRCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        self.assertIsNone(cache.get("key1"))
        self.assertIsNone(cache.get("key2"))
