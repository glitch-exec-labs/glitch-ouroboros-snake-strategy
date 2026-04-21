"""
GlitchExecutor Model 3: Momentum Hunter
Uses RSI momentum breaks with EMA trend filter and volume confirmation.
"""
import numpy as np
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import rsi, ema


class MomentumHunterModel(BaseModel):
    """
    Momentum strategy using:
    - RSI(14) crossing above 52 (bullish) or below 48 (bearish) within last 5 bars
    - Price vs EMA(20) as confidence modifier (not a hard gate)
    - Volume > 1.3x average for confidence boost
    """

    name = "momentum_hunter"
    version = "1.0"

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Run momentum analysis on M15 candles."""
        m15_candles = candles.get("m15")

        min_bars = self.p("min_bars", 50)
        if m15_candles is None or len(m15_candles) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": 0.0,
                "reasoning": "Insufficient M15 candle data for analysis.",
                "indicators": {}
            }

        # Extract OHLCV
        _, highs, lows, closes, volumes = self._extract_ohlcv(m15_candles)

        if closes is None or len(closes) < min_bars:
            return {
                "model": self.name,
                "vote": "HOLD",
                "confidence": 0.0,
                "reasoning": "Invalid close price data.",
                "indicators": {}
            }

        # Calculate indicators
        rsi_period = self.p("rsi_period", 14)
        ema_period = self.p("ema_period", 20)
        volume_window = self.p("volume_window", 50)
        volume_confirmed_mult = self.p("volume_confirmed_mult", 1.3)
        rsi_crossover_lookback = self.p("rsi_crossover_lookback", 5)
        rsi_bullish_cross = self.p("rsi_bullish_cross", 52)
        rsi_bearish_cross = self.p("rsi_bearish_cross", 48)

        rsi_vals = rsi(closes, rsi_period)
        ema_20 = ema(closes, ema_period)

        # Get current values
        current_close = closes[-1]
        current_rsi = rsi_vals[-1] if not np.isnan(rsi_vals[-1]) else 50
        current_ema = ema_20[-1] if len(ema_20) > 0 else current_close
        current_volume = volumes[-1] if volumes is not None else 0

        # Calculate volume average
        vol_avg = np.mean(volumes[-volume_window:]) if volumes is not None and len(volumes) >= volume_window else current_volume
        volume_ratio = current_volume / vol_avg if vol_avg > 0 else 1.0

        # Detect RSI crossover within lookback window
        rsi_crossover = self._detect_rsi_crossover(rsi_vals, rsi_crossover_lookback, rsi_bullish_cross, rsi_bearish_cross)

        # Build indicators dict
        indicators = {
            "rsi": round(float(current_rsi), 2),
            "ema_20": round(float(current_ema), 4),
            "price_above_ema": current_close > current_ema,
            "current_volume": round(float(current_volume), 2),
            "volume_avg_50": round(float(vol_avg), 2),
            "volume_ratio": round(float(volume_ratio), 2),
            "rsi_crossover": rsi_crossover
        }

        # Check conditions — EMA as confidence modifier, not hard gate
        price_above_ema = current_close > current_ema
        price_below_ema = current_close < current_ema
        volume_confirmed = volume_ratio > volume_confirmed_mult

        base_confidence = self.p("base_confidence", 0.65)
        ema_boost = self.p("ema_boost", 0.10)
        volume_boost = self.p("volume_boost", 0.15)
        max_confidence = self.p("max_confidence", 0.95)
        hold_confidence = self.p("hold_confidence", 0.5)

        # Generate signals — RSI crossover is primary, EMA confirms
        if rsi_crossover == "bullish":
            # Bullish momentum detected
            confidence = base_confidence
            notes = []

            # EMA alignment boosts confidence (no longer a gate)
            if price_above_ema:
                confidence += ema_boost
                notes.append("price above EMA(20)")
            else:
                notes.append("price below EMA(20) — reduced confidence")

            # Volume boost
            if volume_confirmed:
                confidence += volume_boost
                notes.append("volume confirmed")

            confidence = min(max_confidence, confidence)
            reasoning = f"RSI broke above 52 — momentum shift to bullish. {', '.join(notes)}."

            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "indicators": indicators
            }

        elif rsi_crossover == "bearish":
            # Bearish momentum detected
            confidence = base_confidence
            notes = []

            # EMA alignment boosts confidence (no longer a gate)
            if price_below_ema:
                confidence += ema_boost
                notes.append("price below EMA(20)")
            else:
                notes.append("price above EMA(20) — reduced confidence")

            # Volume boost
            if volume_confirmed:
                confidence += volume_boost
                notes.append("volume confirmed")

            confidence = min(max_confidence, confidence)
            reasoning = f"RSI broke below 48 — momentum shift to bearish. {', '.join(notes)}."

            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "indicators": indicators
            }

        # No RSI crossover detected
        reasoning = "HOLD: no RSI momentum break in last 5 bars."

        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": reasoning,
            "indicators": indicators
        }

    def _detect_rsi_crossover(self, rsi_vals: np.ndarray, n: int = 5,
                              bull_cross: float = 52, bear_cross: float = 48) -> str:
        """Detect if RSI crossed above bull_cross or below bear_cross within last n bars."""
        if len(rsi_vals) < n + 1 or np.all(np.isnan(rsi_vals)):
            return "none"

        # Get last n+1 valid RSI values
        valid_rsi = rsi_vals[~np.isnan(rsi_vals)]
        if len(valid_rsi) < n + 1:
            return "none"

        recent_rsi = valid_rsi[-(n+1):]

        for i in range(1, len(recent_rsi)):
            prev_rsi = recent_rsi[i-1]
            curr_rsi = recent_rsi[i]

            # Bullish: crossed above bull_cross
            if prev_rsi <= bull_cross and curr_rsi > bull_cross:
                return "bullish"

            # Bearish: crossed below bear_cross
            if prev_rsi >= bear_cross and curr_rsi < bear_cross:
                return "bearish"

        return "none"
