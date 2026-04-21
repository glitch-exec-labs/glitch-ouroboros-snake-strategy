"""
GlitchExecutor Model 1: Trend Follower
Uses SMA/EMA crossover + ADX trend confirmation + ATR volatility filter.
"""
import numpy as np
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import sma, ema, adx, atr


class TrendFollowerModel(BaseModel):
    """
    Trend following strategy using:
    - SMA(9) / EMA(21) crossover detection within last 5 bars
    - ADX > 15 for trend confirmation
    - ATR vs median(ATR, 100) as confidence modifier (not a hard gate)
    """

    name = "trend_follower"
    version = "1.0"

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Run trend following analysis on H1 candles."""
        h1_candles = candles.get("h1")

        min_bars = self.p("min_bars", 50)
        if h1_candles is None or len(h1_candles) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": 0.0,
                "reasoning": "Insufficient H1 candle data for analysis.",
                "indicators": {}
            }

        # Extract OHLCV
        _, highs, lows, closes, _ = self._extract_ohlcv(h1_candles)

        if closes is None or len(closes) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": 0.0,
                "reasoning": "Invalid close price data.",
                "indicators": {}
            }

        sma_period = self.p("sma_period", 9)
        ema_period = self.p("ema_period", 21)
        adx_period = self.p("adx_period", 14)
        atr_period = self.p("atr_period", 14)
        crossover_lookback = self.p("crossover_lookback", 5)
        atr_median_window = self.p("atr_median_window", 100)

        # Calculate indicators
        sma_9 = sma(closes, sma_period)
        ema_21 = ema(closes, ema_period)
        adx_vals = adx(highs, lows, closes, adx_period)
        atr_vals = atr(highs, lows, closes, atr_period)

        # Get current values
        current_close = closes[-1]
        current_adx = adx_vals[-1] if not np.isnan(adx_vals[-1]) else 0
        current_atr = atr_vals[-1] if not np.isnan(atr_vals[-1]) else 0

        # Calculate median ATR over window
        atr_window = atr_vals[-atr_median_window:] if len(atr_vals) >= atr_median_window else atr_vals
        atr_median = np.median(atr_window[~np.isnan(atr_window)]) if len(atr_window) > 0 else 0

        # Detect crossover within last n bars
        crossover = self._detect_crossover_last_n(sma_9, ema_21, crossover_lookback)

        # Build indicators dict
        indicators = {
            "sma_9": round(float(sma_9[-1]), 4) if len(sma_9) > 0 else None,
            "ema_21": round(float(ema_21[-1]), 4) if len(ema_21) > 0 else None,
            "adx": round(float(current_adx), 2),
            "atr": round(float(current_atr), 4),
            "atr_median_100": round(float(atr_median), 4),
            "crossover": crossover
        }

        adx_min_trend = self.p("adx_min_trend", 15)
        adx_strong = self.p("adx_strong", 25)
        adx_mid = self.p("adx_mid", 20)
        strong_confidence = self.p("strong_confidence", 0.9)
        mid_confidence = self.p("mid_confidence", 0.75)
        low_confidence = self.p("low_confidence", 0.6)
        low_vol_penalty = self.p("low_vol_penalty", 0.15)
        min_confidence_floor = self.p("min_confidence_floor", 0.45)
        hold_confidence = self.p("hold_confidence", 0.5)

        # Check conditions
        trend_exists = current_adx > adx_min_trend
        low_volatility = current_atr < atr_median

        # Determine signal — crossover + trend required, ATR is confidence modifier only
        if crossover == "bullish" and trend_exists:
            if current_adx >= adx_strong:
                confidence = strong_confidence
            elif current_adx >= adx_mid:
                confidence = mid_confidence
            else:
                confidence = low_confidence

            # ATR as confidence modifier (not a hard gate)
            if low_volatility:
                confidence = max(min_confidence_floor, confidence - low_vol_penalty)
                atr_note = " Low ATR — reduced confidence."
            else:
                atr_note = ""

            reasoning = f"SMA(9) crossed above EMA(21) with ADX at {current_adx:.1f} (trend confirmed).{atr_note}"

            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "indicators": indicators
            }

        elif crossover == "bearish" and trend_exists:
            if current_adx >= adx_strong:
                confidence = strong_confidence
            elif current_adx >= adx_mid:
                confidence = mid_confidence
            else:
                confidence = low_confidence

            if low_volatility:
                confidence = max(min_confidence_floor, confidence - low_vol_penalty)
                atr_note = " Low ATR — reduced confidence."
            else:
                atr_note = ""

            reasoning = f"SMA(9) crossed below EMA(21) with ADX at {current_adx:.1f} (trend confirmed).{atr_note}"

            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "indicators": indicators
            }

        # No signal
        reasons = []
        if crossover == "none":
            reasons.append("no SMA/EMA crossover in last 5 bars")
        else:
            if not trend_exists:
                reasons.append(f"ADX too low ({current_adx:.1f} < 15)")

        reasoning = "HOLD: " + ", ".join(reasons) if reasons else "HOLD: No trend conditions met."

        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": reasoning,
            "indicators": indicators
        }

    def _detect_crossover_last_n(self, fast_line: np.ndarray, slow_line: np.ndarray, n: int = 3) -> str:
        """Detect if fast line crossed slow line within last n bars."""
        if len(fast_line) < n + 1 or len(slow_line) < n + 1:
            return "none"

        for i in range(1, n + 1):
            curr_idx = -i
            prev_idx = -i - 1

            if abs(prev_idx) > len(fast_line) or abs(prev_idx) > len(slow_line):
                break

            fast_prev = fast_line[prev_idx]
            fast_curr = fast_line[curr_idx]
            slow_prev = slow_line[prev_idx]
            slow_curr = slow_line[curr_idx]

            # Bullish crossover: fast was below, now above
            if fast_prev < slow_prev and fast_curr > slow_curr:
                return "bullish"

            # Bearish crossover: fast was above, now below
            if fast_prev > slow_prev and fast_curr < slow_curr:
                return "bearish"

        return "none"
