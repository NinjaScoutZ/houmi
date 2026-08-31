"""
AI Provider Key Pool Balancer with Smart Failover & Circuit Breaker
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("houmi-key-pool")


class KeyState(BaseModel):
    key_masked: str
    key_value: str
    provider: str
    failure_count: int = 0
    cooldown_until: float = 0.0
    is_active: bool = True
    total_calls: int = 0


class AIKeyPool:
    """
    Manages pools of API keys per provider (Gemini, DeepSeek, Claude, OpenAI).
    Features:
    - Smart Round-Robin Key Rotation
    - Circuit Breaker: Automatically disables rate-limited / failed keys for cooldown duration
    - Automatic Failover across available keys
    """

    def __init__(self, cooldown_seconds: float = 60.0, max_consecutive_failures: int = 3):
        self.cooldown_seconds = cooldown_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self._pools: Dict[str, List[KeyState]] = {}
        self._pointers: Dict[str, int] = {}

    def register_keys(self, provider: str, keys: List[str]) -> None:
        """Register or update active keys for a provider."""
        provider = provider.lower().strip()
        state_list: List[KeyState] = []
        for k in keys:
            k_clean = k.strip()
            if not k_clean:
                continue
            masked = f"{k_clean[:4]}...{k_clean[-4:]}" if len(k_clean) > 8 else "***"
            state_list.append(
                KeyState(
                    key_masked=masked,
                    key_value=k_clean,
                    provider=provider,
                )
            )
        self._pools[provider] = state_list
        self._pointers[provider] = 0
        logger.info(f"Registered {len(state_list)} keys for provider '{provider}'")

    def acquire_key(self, provider: str) -> Optional[str]:
        """
        Acquires the next healthy API key via round-robin.
        Skips keys currently in cooldown.
        """
        provider = provider.lower().strip()
        pool = self._pools.get(provider, [])
        if not pool:
            return None

        now = time.time()
        start_idx = self._pointers.get(provider, 0)
        n = len(pool)

        for i in range(n):
            idx = (start_idx + i) % n
            candidate = pool[idx]

            # Check if cooldown has expired
            if candidate.cooldown_until > 0 and now >= candidate.cooldown_until:
                candidate.cooldown_until = 0.0
                candidate.failure_count = 0
                candidate.is_active = True

            if candidate.is_active and candidate.cooldown_until == 0.0:
                self._pointers[provider] = (idx + 1) % n
                candidate.total_calls += 1
                return candidate.key_value

        logger.warning(f"All keys for provider '{provider}' are currently in cooldown or disabled.")
        return None

    def report_success(self, provider: str, key_value: str) -> None:
        """Reset failure counters upon successful API call."""
        provider = provider.lower().strip()
        for state in self._pools.get(provider, []):
            if state.key_value == key_value:
                state.failure_count = 0
                state.cooldown_until = 0.0
                break

    def report_failure(
        self,
        provider: str,
        key_value: str,
        is_rate_limit: bool = False,
        custom_cooldown: Optional[float] = None,
    ) -> None:
        """
        Report an error (e.g. 429 Rate Limit or 503 Overloaded).
        Triggers cooldown or disables key if consecutive failures exceed threshold.
        """
        provider = provider.lower().strip()
        now = time.time()
        duration = custom_cooldown or (120.0 if is_rate_limit else self.cooldown_seconds)

        for state in self._pools.get(provider, []):
            if state.key_value == key_value:
                state.failure_count += 1
                if is_rate_limit or state.failure_count >= self.max_consecutive_failures:
                    state.cooldown_until = now + duration
                    logger.warning(
                        f"Key {state.key_masked} on '{provider}' placed on cooldown for {duration}s (Failures: {state.failure_count})"
                    )
                break

    def get_pool_status(self) -> Dict[str, Any]:
        """Return real-time health telemetry of all registered key pools."""
        now = time.time()
        result: Dict[str, Any] = {}
        for provider, pool in self._pools.items():
            total = len(pool)
            active = sum(1 for k in pool if k.is_active and (k.cooldown_until == 0 or now >= k.cooldown_until))
            cooling = sum(1 for k in pool if k.cooldown_until > now)
            result[provider] = {
                "total_keys": total,
                "active_keys": active,
                "cooldown_keys": cooling,
                "all_healthy": active == total,
            }
        return result


key_pool = AIKeyPool()
