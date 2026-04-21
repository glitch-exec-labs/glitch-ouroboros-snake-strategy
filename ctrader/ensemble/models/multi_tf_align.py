"""
GlitchExecutor Model 5: Multi-Timeframe Alignment
Checks trend direction across M15, H1, and H4 timeframes for confirmation.
"""
import numpy as np
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import ema


class MultiTFAlignModel(BaseModel):
    """
    Multi-timeframe alignment strategy:
    - Checks if price is above/below EMA(20) on M15, H1, and H4
    - All 3 align = strong signal (0.9 confidence)
    - 2/3 align (incl. conflicting) = signal at varying confidence
    - Truly mixed (1/1/1) = HOLD
    """

    name = "multi_tf_align"
    version = "1.0"

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Check trend alignment across M15, H1, and H4."""

        three_aligned_confidence = self.p("three_aligned_confidence", 0.9)
        two_zero_confidence = self.p("two_zero_confidence", 0.6)
        two_one_confidence = self.p("two_one_confidence", 0.45)
        hold_confidence = self.p("hold_confidence", 0.5)

        # Check each timeframe
        m15_trend = self._get_trend_direction(candles.get("m15"))
        h1_trend = self._get_trend_direction(candles.get("h1"))
        h4_trend = self._get_trend_direction(candles.get("h4"))

        # Count bullish and bearish signals
        bullish_count = sum(1 for t in [m15_trend, h1_trend, h4_trend] if t == "bullish")
        bearish_count = sum(1 for t in [m15_trend, h1_trend, h4_trend] if t == "bearish")

        # Build indicators
        indicators = {
            "m15_trend": m15_trend,
            "h1_trend": h1_trend,
            "h4_trend": h4_trend,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count
        }

        # Determine alignment and generate signal
        if bullish_count == 3:
            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": three_aligned_confidence,
                "reasoning": "All 3 timeframes (M15, H1, H4) aligned bullish — strong trend confirmation.",
                "indicators": indicators
            }

        elif bearish_count == 3:
            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": three_aligned_confidence,
                "reasoning": "All 3 timeframes (M15, H1, H4) aligned bearish — strong trend confirmation.",
                "indicators": indicators
            }

        elif bullish_count == 2 and bearish_count == 0:
            agreeing_tfs = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bullish"]

            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": two_zero_confidence,
                "reasoning": f"2/3 timeframes aligned bullish ({', '.join(agreeing_tfs)}) — moderate trend confirmation.",
                "indicators": indicators
            }

        elif bearish_count == 2 and bullish_count == 0:
            agreeing_tfs = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bearish"]

            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": two_zero_confidence,
                "reasoning": f"2/3 timeframes aligned bearish ({', '.join(agreeing_tfs)}) — moderate trend confirmation.",
                "indicators": indicators
            }

        elif bullish_count == 2 and bearish_count == 1:
            agreeing_tfs = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bullish"]
            opposing_tf = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bearish"][0]

            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": two_one_confidence,
                "reasoning": f"2/3 timeframes bullish ({', '.join(agreeing_tfs)}) but {opposing_tf} bearish — weak bullish lean.",
                "indicators": indicators
            }

        elif bearish_count == 2 and bullish_count == 1:
            agreeing_tfs = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bearish"]
            opposing_tf = [tf for tf, trend in [("M15", m15_trend), ("H1", h1_trend), ("H4", h4_trend)] if trend == "bullish"][0]

            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": two_one_confidence,
                "reasoning": f"2/3 timeframes bearish ({', '.join(agreeing_tfs)}) but {opposing_tf} bullish — weak bearish lean.",
                "indicators": indicators
            }

        # Truly mixed signals
        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": f"Mixed timeframe signals (bullish: {bullish_count}, bearish: {bearish_count}) — no clear trend alignment.",
            "indicators": indicators
        }

    def _get_trend_direction(self, candles: np.ndarray) -> str:
        """Determine trend direction on a timeframe using EMA."""
        min_bars = self.p("min_bars", 30)
        ema_period = self.p("ema_period", 20)
        trend_threshold_pct = self.p("trend_threshold_pct", 0.0003)

        if candles is None or len(candles) < min_bars:
            return "neutral"

        # Extract close prices
        closes = candles[:, 4] if candles.shape[1] > 4 else None
        if closes is None or len(closes) < min_bars:
            return "neutral"

        # Calculate EMA
        ema_20 = ema(closes, ema_period)

        if len(ema_20) < 5:
            return "neutral"

        # Get current price and EMA
        current_price = closes[-1]
        current_ema = ema_20[-1]

        # Determine trend with threshold to avoid noise
        threshold = current_ema * trend_threshold_pct

        if current_price > current_ema + threshold:
            return "bullish"
        elif current_price < current_ema - threshold:
            return "bearish"
        return "neutral"
