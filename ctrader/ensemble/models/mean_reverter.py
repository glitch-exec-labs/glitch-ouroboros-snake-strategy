"""
GlitchExecutor Model 2: Mean Reverter
Uses Bollinger Bands + RSI for mean reversion signals in ranging markets.
"""
import numpy as np
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import bollinger_bands, rsi, adx


class MeanReverterModel(BaseModel):
    """
    Mean reversion strategy using:
    - Price outside Bollinger Bands (20, 2.0) — primary signal
    - RSI confirmation (< 35 oversold, > 65 overbought)
    - ADX < 30 confirming ranging market (not trending)
    - Secondary signal: price near BB band (within 0.3x width) with mild RSI
    """

    name = "mean_reverter"
    version = "1.0"

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Run mean reversion analysis on H1 candles."""
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

        # Calculate indicators
        bb_period = self.p("bb_period", 20)
        bb_std = self.p("bb_std", 2.0)
        rsi_period = self.p("rsi_period", 14)
        adx_period = self.p("adx_period", 14)

        upper_bb, middle_bb, lower_bb = bollinger_bands(closes, bb_period, bb_std)
        rsi_vals = rsi(closes, rsi_period)
        adx_vals = adx(highs, lows, closes, adx_period)

        # Get current values
        current_close = closes[-1]
        current_upper = upper_bb[-1]
        current_lower = lower_bb[-1]
        current_rsi = rsi_vals[-1] if not np.isnan(rsi_vals[-1]) else 50
        current_adx = adx_vals[-1] if not np.isnan(adx_vals[-1]) else 0

        # Build indicators dict
        indicators = {
            "close": round(float(current_close), 4),
            "bb_upper": round(float(current_upper), 4),
            "bb_lower": round(float(current_lower), 4),
            "rsi": round(float(current_rsi), 2),
            "adx": round(float(current_adx), 2),
            "bb_position": "below" if current_close < current_lower else "above" if current_close > current_upper else "inside"
        }

        adx_ranging_threshold = self.p("adx_ranging_threshold", 30)
        rsi_oversold = self.p("rsi_oversold", 35)
        rsi_overbought = self.p("rsi_overbought", 65)
        near_band_pct = self.p("near_band_pct", 0.3)
        mild_oversold_thr = self.p("mild_oversold", 42)
        mild_overbought_thr = self.p("mild_overbought", 58)
        base_confidence = self.p("base_confidence", 0.6)
        rsi_extreme_scale = self.p("rsi_extreme_scale", 0.2)
        bb_distance_scale = self.p("bb_distance_scale", 0.5)
        bb_distance_cap = self.p("bb_distance_cap", 0.2)
        max_confidence = self.p("max_confidence", 0.95)
        secondary_confidence = self.p("secondary_confidence", 0.55)
        hold_confidence = self.p("hold_confidence", 0.5)

        # Check ranging market condition
        is_ranging = current_adx < adx_ranging_threshold

        # BB band width for proximity calculations
        bb_width = current_upper - current_lower if (current_upper - current_lower) > 0 else 0.0001

        # Check for oversold (potential BUY)
        is_below_bb = current_close < current_lower
        is_oversold = current_rsi < rsi_oversold

        # Check for overbought (potential SELL)
        is_above_bb = current_close > current_upper
        is_overbought = current_rsi > rsi_overbought

        # Secondary signal: price near BB band with mild RSI
        near_lower = current_close < (current_lower + bb_width * near_band_pct)
        near_upper = current_close > (current_upper - bb_width * near_band_pct)
        mild_oversold = current_rsi < mild_oversold_thr
        mild_overbought = current_rsi > mild_overbought_thr

        # Generate signals if ranging
        if is_ranging:
            # Primary signal: price outside BB + RSI extreme
            if is_below_bb and is_oversold:
                rsi_extreme = max(0, (rsi_oversold - current_rsi) / rsi_oversold)
                bb_distance = (current_lower - current_close) / bb_width
                confidence = base_confidence + (rsi_extreme * rsi_extreme_scale) + (min(bb_distance, bb_distance_cap) * bb_distance_scale)
                confidence = min(max_confidence, confidence)

                reasoning = f"Price below lower BB ({current_close:.2f} < {current_lower:.2f}) with RSI oversold at {current_rsi:.1f} in ranging market (ADX {current_adx:.1f})."

                return {
                    "model": self.name,
                    "vote": "BUY",
                    "confidence": round(confidence, 2),
                    "reasoning": reasoning,
                    "indicators": indicators
                }

            elif is_above_bb and is_overbought:
                rsi_extreme = max(0, (current_rsi - rsi_overbought) / rsi_oversold)
                bb_distance = (current_close - current_upper) / bb_width
                confidence = base_confidence + (rsi_extreme * rsi_extreme_scale) + (min(bb_distance, bb_distance_cap) * bb_distance_scale)
                confidence = min(max_confidence, confidence)

                reasoning = f"Price above upper BB ({current_close:.2f} > {current_upper:.2f}) with RSI overbought at {current_rsi:.1f} in ranging market (ADX {current_adx:.1f})."

                return {
                    "model": self.name,
                    "vote": "SELL",
                    "confidence": round(confidence, 2),
                    "reasoning": reasoning,
                    "indicators": indicators
                }

            # Secondary signal: price near BB + mild RSI (weaker signal)
            elif near_lower and mild_oversold and not is_above_bb:
                confidence = secondary_confidence
                reasoning = f"Price approaching lower BB ({current_close:.2f} near {current_lower:.2f}) with RSI leaning oversold at {current_rsi:.1f}. Weaker mean reversion signal."

                return {
                    "model": self.name,
                    "vote": "BUY",
                    "confidence": round(confidence, 2),
                    "reasoning": reasoning,
                    "indicators": indicators
                }

            elif near_upper and mild_overbought and not is_below_bb:
                confidence = secondary_confidence
                reasoning = f"Price approaching upper BB ({current_close:.2f} near {current_upper:.2f}) with RSI leaning overbought at {current_rsi:.1f}. Weaker mean reversion signal."

                return {
                    "model": self.name,
                    "vote": "SELL",
                    "confidence": round(confidence, 2),
                    "reasoning": reasoning,
                    "indicators": indicators
                }

        # No signal
        reasons = []
        if not is_ranging:
            reasons.append(f"trending market (ADX {current_adx:.1f})")
        if not is_below_bb and not is_above_bb and not near_lower and not near_upper:
            reasons.append("price within BB bands")
        if is_below_bb and not is_oversold:
            reasons.append(f"RSI not oversold ({current_rsi:.1f})")
        if is_above_bb and not is_overbought:
            reasons.append(f"RSI not overbought ({current_rsi:.1f})")

        reasoning = "HOLD: " + ", ".join(reasons) if reasons else "HOLD: No mean reversion conditions met."

        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": reasoning,
            "indicators": indicators
        }
