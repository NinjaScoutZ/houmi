"""
Houmi Studio - Adaptive Screentone Halftone Inpainter
Production Engine for Phase-Locked Halftone Resynthesis without Gray Blur.
"""

from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class ScreentoneParameters:
    f0: float                 # Fundamental spatial frequency (cycles / pixel)
    period: float             # Dot pitch T (pixels / dot)
    theta_deg: float          # Screen angle in degrees [0, 90)
    theta_rad: float          # Screen angle in radians
    lpi: float                # Lines Per Inch at specified DPI
    phi_u: float              # Phase offset along primary lattice vector (radians)
    phi_v: float              # Phase offset along secondary lattice vector (radians)
    confidence: float         # Spectral peak prominence score [0.0, 1.0]
    is_screentone: bool       # True if reliable periodic dot pattern detected


class AdaptiveScreentoneInpainter:
    """
    Adaptive Screentone Halftone Inpainter.
    Decomposes screentoned manga panels using 2D FFT and Scale-Tuned Rolling Guidance Filtering (RGF),
    smoothly inpaints the base continuous-tone shading field, and resynthesizes phase-locked binary dots.
    """

    def __init__(self, dpi: int = 600, min_lpi: float = 25.0, max_lpi: float = 120.0):
        self.dpi = float(dpi)
        self.min_freq = min_lpi / self.dpi
        self.max_freq = max_lpi / self.dpi

    def extract_screentone_parameters(
        self,
        image_gray: np.ndarray,
        mask: Optional[np.ndarray] = None,
        patch_size: int = 256
    ) -> ScreentoneParameters:
        """
        Extracts screentone parameters (f0, theta, LPI, phase) using 2D FFT
        with Hann windowing, DC notch filtering, and 2D quadratic sub-pixel peak interpolation.
        """
        h, w = image_gray.shape[:2]
        
        # Select representative patch outside the inpainting mask if possible
        if mask is not None and np.count_nonzero(mask) > 0:
            unmasked = (mask == 0).astype(np.uint8) * 255
            dist_map = cv2.distanceTransform(unmasked, cv2.DIST_L2, 5)
            _, max_val, _, max_loc = cv2.minMaxLoc(dist_map)
            radius = int(max_val)
            if radius >= 32:
                crop_size = min(patch_size, radius * 2)
                cx, cy = max_loc
                x0 = max(0, min(w - crop_size, cx - crop_size // 2))
                y0 = max(0, min(h - crop_size, cy - crop_size // 2))
                patch = image_gray[y0:y0+crop_size, x0:x0+crop_size].astype(np.float32)
                origin_offset = (float(x0), float(y0))
            else:
                patch = image_gray.astype(np.float32)
                origin_offset = (0.0, 0.0)
        else:
            cw, ch = min(w, patch_size), min(h, patch_size)
            x0, y0 = (w - cw) // 2, (h - ch) // 2
            patch = image_gray[y0:y0+ch, x0:x0+cw].astype(np.float32)
            origin_offset = (float(x0), float(y0))

        ph, pw = patch.shape[:2]
        if ph < 32 or pw < 32:
            return ScreentoneParameters(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)

        # 1. 2D Hann Windowing to eliminate spectral leakage
        win_y = np.hanning(ph)
        win_x = np.hanning(pw)
        window_2d = np.outer(win_y, win_x).astype(np.float32)
        
        patch_demean = patch - np.mean(patch)
        patch_windowed = patch_demean * window_2d

        # 2. 2D FFT & Log Power Spectral Density
        fft2 = np.fft.fft2(patch_windowed)
        fft_shift = np.fft.fftshift(fft2)
        psd = np.abs(fft_shift) ** 2
        log_psd = np.log1p(psd)

        cy, cx = ph // 2, pw // 2

        # 3. Frequency grid in cycles/pixel
        u_freq = (np.arange(pw) - cx) / float(pw)
        v_freq = (np.arange(ph) - cy) / float(ph)
        U, V = np.meshgrid(u_freq, v_freq)
        R_freq = np.sqrt(U**2 + V**2)

        # 4. DC & Cross-axis Notch Filter
        notch_mask = np.ones((ph, pw), dtype=np.float32)
        notch_mask[R_freq < self.min_freq] = 0.0
        notch_mask[R_freq > self.max_freq] = 0.0
        notch_mask[np.abs(U) < (1.5 / pw)] *= 0.2
        notch_mask[np.abs(V) < (1.5 / ph)] *= 0.2

        filtered_psd = log_psd * notch_mask

        # Look only in upper half-plane (Hermitian symmetry)
        upper_half = filtered_psd.copy()
        upper_half[cy:, :] = 0.0

        max_idx = np.argmax(upper_half)
        py, px = np.unravel_index(max_idx, upper_half.shape)
        peak_val = upper_half[py, px]

        # Background noise level for peak prominence calculation
        ring_mask = (R_freq >= self.min_freq) & (R_freq <= self.max_freq)
        bg_mean = float(np.mean(log_psd[ring_mask])) if np.any(ring_mask) else 1.0
        bg_std = float(np.std(log_psd[ring_mask])) if np.any(ring_mask) else 1.0
        prominence = (peak_val - bg_mean) / (bg_std + 1e-6)

        if prominence < 2.5 or peak_val <= 0:
            return ScreentoneParameters(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)

        # 5. Sub-pixel quadratic interpolation
        def quadratic_subpixel(val_l: float, val_c: float, val_r: float) -> float:
            denom = 2.0 * (2.0 * val_c - val_l - val_r)
            if abs(denom) < 1e-7:
                return 0.0
            return float((val_r - val_l) / denom)

        delta_x = 0.0
        if 0 < px < pw - 1:
            delta_x = quadratic_subpixel(
                float(log_psd[py, px - 1]), float(log_psd[py, px]), float(log_psd[py, px + 1])
            )
            delta_x = float(np.clip(delta_x, -0.5, 0.5))

        delta_y = 0.0
        if 0 < py < ph - 1:
            delta_y = quadratic_subpixel(
                float(log_psd[py - 1, px]), float(log_psd[py, px]), float(log_psd[py + 1, px])
            )
            delta_y = float(np.clip(delta_y, -0.5, 0.5))

        sub_u = (float(px) + delta_x - cx) / float(pw)
        sub_v = (float(py) + delta_y - cy) / float(ph)

        f0 = float(np.sqrt(sub_u**2 + sub_v**2))
        period = 1.0 / f0 if f0 > 0 else 0.0
        lpi = f0 * self.dpi

        theta_rad = float(np.arctan2(sub_v, sub_u)) % (np.pi / 2.0)
        theta_deg = float(np.degrees(theta_rad))

        complex_val = fft_shift[py, px]
        raw_phase = float(np.angle(complex_val))
        phi_u = float((raw_phase - 2.0 * np.pi * (sub_u * origin_offset[0] + sub_v * origin_offset[1])) % (2.0 * np.pi))
        
        rot_u = -sub_v
        rot_v = sub_u
        py2 = int(np.clip(round(cy + rot_v * ph), 0, ph - 1))
        px2 = int(np.clip(round(cx + rot_u * pw), 0, pw - 1))
        complex_val2 = fft_shift[py2, px2]
        raw_phase2 = float(np.angle(complex_val2))
        phi_v = float((raw_phase2 - 2.0 * np.pi * (rot_u * origin_offset[0] + rot_v * origin_offset[1])) % (2.0 * np.pi))

        confidence = float(np.clip(prominence / 10.0, 0.0, 1.0))

        return ScreentoneParameters(
            f0=f0, period=period, theta_deg=theta_deg, theta_rad=theta_rad,
            lpi=lpi, phi_u=phi_u, phi_v=phi_v, confidence=confidence, is_screentone=True
        )

    def dual_band_bilateral_decomposition(
        self,
        image_gray: np.ndarray,
        params: ScreentoneParameters,
        iterations: int = 4
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Decomposes image into:
        - Base Layer B: continuous tone / shading (scale-tuned RGF with sigma_s = T / sqrt(2))
        - Texture Layer T: high-frequency dot lattice residual
        """
        if not params.is_screentone or params.period <= 0:
            return image_gray.copy(), np.zeros_like(image_gray)

        sigma_s = max(1.5, params.period / np.sqrt(2.0))
        sigma_r = 25.5

        img_f = image_gray.astype(np.float32)

        # Scale space Gaussian filtering
        ksize = int(np.ceil(sigma_s * 3.0)) * 2 + 1
        guidance = cv2.GaussianBlur(img_f, (ksize, ksize), sigmaX=sigma_s, sigmaY=sigma_s)

        # Iterative Joint Bilateral Guidance Refinement
        d = max(5, int(sigma_s * 2.0) | 1)
        for _ in range(iterations):
            guidance = cv2.bilateralFilter(
                src=img_f,
                d=d,
                sigmaColor=sigma_r,
                sigmaSpace=sigma_s
            )

        base = np.clip(guidance, 0, 255).astype(np.uint8)
        texture = cv2.subtract(image_gray, base)

        return base, texture

    def inpaint_base_layer(
        self,
        base_gray: np.ndarray,
        mask: np.ndarray
    ) -> np.ndarray:
        """
        Inpaints the smooth base layer using Navier-Stokes / Biharmonic gradient propagation.
        """
        if np.count_nonzero(mask) == 0:
            return base_gray.copy()
            
        inpainted = cv2.inpaint(base_gray, mask, inpaintRadius=5, flags=cv2.INPAINT_NS)
        return inpainted

    def synthesize_halftone(
        self,
        base_inpainted: np.ndarray,
        params: ScreentoneParameters,
        dot_shape: str = "circle",
        dot_gain_gamma: float = 1.0
    ) -> np.ndarray:
        """
        Synthesizes discrete binary halftone dots {0, 255} phase-locked with the surrounding canvas.
        """
        h, w = base_inpainted.shape[:2]
        
        y_coords, x_coords = np.mgrid[0:h, 0:w].astype(np.float32)
        
        cos_t = np.cos(params.theta_rad)
        sin_t = np.sin(params.theta_rad)

        u_rot = x_coords * cos_t + y_coords * sin_t
        v_rot = -x_coords * sin_t + y_coords * cos_t

        u_norm = params.f0 * u_rot + (params.phi_u / (2.0 * np.pi))
        v_norm = params.f0 * v_rot + (params.phi_v / (2.0 * np.pi))

        xi = u_norm - np.floor(u_norm)
        eta = v_norm - np.floor(v_norm)

        dist_center = np.sqrt((xi - 0.5)**2 + (eta - 0.5)**2)
        screen = np.clip(1.0 - (2.0 * np.sqrt(2.0) * dist_center), 0.0, 1.0)

        norm_base = base_inpainted.astype(np.float32) / 255.0
        ink_coverage = np.clip(1.0 - norm_base, 0.0, 1.0)
        
        if abs(dot_gain_gamma - 1.0) > 1e-3:
            ink_coverage = np.power(ink_coverage, dot_gain_gamma)

        binary_dots = np.where(screen < ink_coverage, np.uint8(0), np.uint8(255))
        return binary_dots

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray
    ) -> np.ndarray:
        """
        Complete end-to-end Adaptive Screentone Inpainting pipeline.
        """
        is_color = (image.ndim == 3 and image.shape[2] == 3)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if is_color else image.copy()

        params = self.extract_screentone_parameters(gray, mask)

        if not params.is_screentone:
            clean_base = cv2.inpaint(gray, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
            if is_color:
                return cv2.cvtColor(clean_base, cv2.COLOR_GRAY2BGR)
            return clean_base

        base, _ = self.dual_band_bilateral_decomposition(gray, params)
        base_inpainted = self.inpaint_base_layer(base, mask)
        halftone_synth = self.synthesize_halftone(base_inpainted, params, dot_shape="circle")

        result_gray = gray.copy()
        mask_binary = (mask > 0)
        result_gray[mask_binary] = halftone_synth[mask_binary]

        if is_color:
            return cv2.cvtColor(result_gray, cv2.COLOR_GRAY2BGR)
        return result_gray
