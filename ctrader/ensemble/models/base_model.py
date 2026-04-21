"""
GlitchExecutor Ensemble Models
Base class for all trading analysis modules.

Parameter loading
-----------------
Each concrete model may ship a JSON params file next to its .py:

    momentum_hunter.py
    momentum_hunter.params.example.json   ← public demo defaults (in git)
    momentum_hunter.params.json           ← real tuning (gitignored)

At __init__ time the model loads params.json if present, else params.example.json.
Access values via self.p("name", default) — if a key is absent from the loaded
params, the fallback default (typically the original hardcoded literal) is used.
This lets every model be tuned in production without touching code, and keeps
the tuned numbers out of the public repo.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any

import numpy as np

_logger = logging.getLogger("ensemble.models")


class BaseModel(ABC):
    """Abstract base class all models must implement."""

    name: str = "base_model"
    version: str = "1.0"

    def __init__(self) -> None:
        self.params: Dict[str, Any] = self._load_params()

    # ── Params loading ─────────────────────────────────────────────────────────────

    def _params_dir(self) -> Path:
        # Models live next to their .py file; params sit alongside.
        import inspect
        return Path(inspect.getfile(self.__class__)).parent

    def _load_params(self) -> Dict[str, Any]:
        d = self._params_dir()
        real = d / f"{self.name}.params.json"
        demo = d / f"{self.name}.params.example.json"
        chosen = real if real.exists() else (demo if demo.exists() else None)
        if chosen is None:
            return {}
        try:
            with open(chosen) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                _logger.warning("%s params is not a dict, ignoring", chosen)
                return {}
            _logger.info("%s loaded params from %s", self.name, chosen.name)
            return data
        except Exception:
            _logger.exception("failed to load %s params from %s", self.name, chosen)
            return {}

    def p(self, key: str, default: Any) -> Any:
        """Fetch a tuning parameter, falling back to the hardcoded default."""
        return self.params.get(key, default)
    
    @abstractmethod
    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        Analyze market data and return trading signal.
        
        Input:
            symbol: "BTCUSD", "EURUSD", etc.
            candles: {
                "m15": numpy array of [time, open, high, low, close, volume] — last 300 bars,
                "h1": numpy array — last 200 bars,
                "h4": numpy array — last 200 bars
            }
        
        Output:
            {
                "model": self.name,
                "vote": "BUY" | "SELL" | "HOLD",
                "confidence": float 0.0-1.0,
                "reasoning": str (1-2 sentences explaining why),
                "indicators": dict (key indicator values used in decision)
            }
        """
        raise NotImplementedError
    
    def _extract_ohlcv(self, candles: np.ndarray) -> tuple:
        """Extract OHLCV columns from candle array."""
        if candles is None or len(candles) == 0:
            return None, None, None, None, None
        
        time_col = candles[:, 0] if candles.shape[1] > 0 else None
        open_col = candles[:, 1] if candles.shape[1] > 1 else None
        high_col = candles[:, 2] if candles.shape[1] > 2 else None
        low_col = candles[:, 3] if candles.shape[1] > 3 else None
        close_col = candles[:, 4] if candles.shape[1] > 4 else None
        volume_col = candles[:, 5] if candles.shape[1] > 5 else None
        
        return open_col, high_col, low_col, close_col, volume_col
    
    def _safe_get_latest(self, arr: np.ndarray, n: int = 1) -> float:
        """Safely get the latest n values from an array."""
        if arr is None or len(arr) == 0:
            return None
        if n == 1:
            return float(arr[-1]) if not np.isnan(arr[-1]) else None
        return arr[-n:] if len(arr) >= n else arr
