"""
GlitchExecutor Model 6: Volume Profiler
Confirms favorable trading conditions using ATR percentile and volume analysis.
"""
import numpy as np
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import atr, ema


class VolumeProfilerModel(BaseModel):
    """
    Volume and volatility confirmation strategy:
    - ATR > 55th percentile (above-average volatility)
    - Volume > 1.2x average (participation confirmed)
    - Direction from EMA(20) slope
    - Partial fallback: one condition met = weak signal in EMA direction
    """

    name = "volume_profiler"
    version = "1.0"

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Analyze volume and volatility conditions on H1 candles."""
        h1_candles = candles.get("h1")

        min_bars = self.p("min_bars", 100)
        hold_confidence = self.p("hold_confidence", 0.5)

        if h1_candles is None or len(h1_candles) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": hold_confidence,
                "reasoning": "Insufficient H1 data for volume profiling.",
                "indicators": {}
            }

        # Extract OHLCV
        _, highs, lows, closes, volumes = self._extract_ohlcv(h1_candles)

        if closes is None or len(closes) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": hold_confidence,
                "reasoning": "Invalid close price data.",
                "indicators": {}
            }

        atr_period = self.p("atr_period", 14)
        atr_percentile_window = self.p("atr_percentile_window", 100)
        atr_percentile_threshold = self.p("atr_percentile_threshold", 55)
        ema_period = self.p("ema_period", 20)
        ema_slope_window = self.p("ema_slope_window", 10)
        volume_window = self.p("volume_window", 50)
        volume_mult_threshold = self.p("volume_mult_threshold", 1.2)
        both_favorable_confidence = self.p("both_favorable_confidence", 0.8)
        partial_favorable_confidence = self.p("partial_favorable_confidence", 0.4)

        # Calculate ATR and percentile
        atr_vals = atr(highs, lows, closes, atr_period)
        current_atr = atr_vals[-1] if not np.isnan(atr_vals[-1]) else 0

        # ATR percentile
        atr_window_vals = atr_vals[-atr_percentile_window:] if len(atr_vals) >= atr_percentile_window else atr_vals
        atr_clean = atr_window_vals[~np.isnan(atr_window_vals)]
        atr_percentile = (np.sum(atr_clean < current_atr) / len(atr_clean)) * 100 if len(atr_clean) > 0 else 50

        # Volume analysis
        if volumes is not None and len(volumes) >= volume_window:
            current_volume = volumes[-1]
            vol_avg_50 = np.mean(volumes[-volume_window:])
            volume_ratio = current_volume / vol_avg_50 if vol_avg_50 > 0 else 1.0
        else:
            current_volume = 0
            vol_avg_50 = 0
            volume_ratio = 1.0

        # EMA direction for bias
        ema_20 = ema(closes, ema_period)
        if len(ema_20) >= ema_slope_window:
            ema_slope = ema_20[-1] - ema_20[-ema_slope_window]
            ema_direction = "rising" if ema_slope > 0 else "falling"
        else:
            ema_direction = "flat"

        # Build indicators
        indicators = {
            "atr": round(float(current_atr), 4),
            "atr_percentile": round(float(atr_percentile), 1),
            "current_volume": round(float(current_volume), 2),
            "volume_avg_50": round(float(vol_avg_50), 2),
            "volume_ratio": round(float(volume_ratio), 2),
            "ema_direction": ema_direction
        }

        # Check favorable conditions
        high_volatility = atr_percentile > atr_percentile_threshold
        high_volume = volume_ratio > volume_mult_threshold
        both_favorable = high_volatility and high_volume
        one_favorable = high_volatility or high_volume

        if both_favorable and ema_direction != "flat":
            if ema_direction == "rising":
                return {
                    "model": self.name,
                    "vote": "BUY",
                    "confidence": both_favorable_confidence,
                    "reasoning": f"Favorable conditions: ATR at {atr_percentile:.0f}th percentile, volume {volume_ratio:.1f}x average. EMA rising confirms bullish bias.",
                    "indicators": indicators
                }
            else:
                return {
                    "model": self.name,
                    "vote": "SELL",
                    "confidence": both_favorable_confidence,
                    "reasoning": f"Favorable conditions: ATR at {atr_percentile:.0f}th percentile, volume {volume_ratio:.1f}x average. EMA falling confirms bearish bias.",
                    "indicators": indicators
                }

        elif one_favorable and ema_direction != "flat":
            met = "ATR above average" if high_volatility else f"volume at {volume_ratio:.1f}x"
            missing = f"volume at {volume_ratio:.1f}x (< 1.2x)" if not high_volume else f"ATR at {atr_percentile:.0f}th percentile (< 55)"

            if ema_direction == "rising":
                return {
                    "model": self.name,
                    "vote": "BUY",
                    "confidence": partial_favorable_confidence,
                    "reasoning": f"Partial conditions: {met} but {missing}. EMA rising — weak bullish lean.",
                    "indicators": indicators
                }
            else:
                return {
                    "model": self.name,
                    "vote": "SELL",
                    "confidence": partial_favorable_confidence,
                    "reasoning": f"Partial conditions: {met} but {missing}. EMA falling — weak bearish lean.",
                    "indicators": indicators
                }

        # No conditions met or flat EMA
        reasons = []
        if not high_volatility:
            reasons.append(f"ATR at {atr_percentile:.0f}th percentile (< 55)")
        if not high_volume:
            reasons.append(f"volume at {volume_ratio:.1f}x (< 1.2x)")
        if ema_direction == "flat":
            reasons.append("flat EMA — no directional bias")

        reasoning = "HOLD: " + ", ".join(reasons) if reasons else "HOLD: No favorable conditions."

        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": reasoning,
            "indicators": indicators
        }
