"""
GlitchExecutor Model 7: Session Analyst
Analyzes trading session quality and adjusts confidence based on market hours.
"""
import numpy as np
from datetime import datetime
from typing import Dict, Any
from .base_model import BaseModel
from .indicators import ema


class SessionAnalystModel(BaseModel):
    """
    Trading session analysis:
    - London session: 7-16 UTC
    - New York session: 12-21 UTC
    - Overlap: 12-16 UTC (strongest)
    - Asian session: 0-7 UTC (weakest for forex — low confidence, not blocked)
    - All sessions can produce signals, confidence varies by session quality
    """

    name = "session_analyst"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.forex_symbols = self.p("forex_symbols",
            ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USOUSD", "AUDUSD", "USDCAD"])

    def analyze(self, symbol: str, candles: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """Analyze current session and return bias based on EMA direction."""

        asian_start = self.p("asian_start", 0)
        asian_end = self.p("asian_end", 7)
        london_start = self.p("london_start", 7)
        london_end = self.p("london_end", 16)
        ny_start = self.p("ny_start", 12)
        ny_end = self.p("ny_end", 21)
        overlap_start = self.p("overlap_start", 12)
        overlap_end = self.p("overlap_end", 16)
        overlap_confidence = self.p("overlap_confidence", 0.9)
        primary_confidence = self.p("primary_confidence", 0.8)
        asian_forex_confidence = self.p("asian_forex_confidence", 0.5)
        asian_crypto_confidence = self.p("asian_crypto_confidence", 0.7)
        asian_crypto_penalty = self.p("asian_crypto_penalty", 0.9)
        hold_confidence = self.p("hold_confidence", 0.5)

        # Get current UTC time
        now = datetime.utcnow()
        hour_utc = now.hour

        # Determine session
        is_asian = asian_start <= hour_utc < asian_end
        is_london = london_start <= hour_utc < london_end
        is_ny = ny_start <= hour_utc < ny_end
        is_overlap = overlap_start <= hour_utc < overlap_end

        # Determine symbol type
        symbol_upper = symbol.upper()
        is_forex = symbol_upper in self.forex_symbols
        is_crypto = not is_forex

        # Get trend direction from H1 EMA
        h1_candles = candles.get("h1")
        ema_direction = self._get_ema_direction(h1_candles)

        # Build indicators
        indicators = {
            "hour_utc": hour_utc,
            "is_asian": is_asian,
            "is_london": is_london,
            "is_ny": is_ny,
            "is_overlap": is_overlap,
            "is_forex": is_forex,
            "is_crypto": is_crypto,
            "ema_direction": ema_direction
        }

        # Session quality assessment
        if is_overlap:
            session_quality = "excellent"
            base_confidence = overlap_confidence
        elif is_london or is_ny:
            session_quality = "good"
            base_confidence = primary_confidence
        elif is_asian:
            session_quality = "poor" if is_forex else "fair"
            base_confidence = asian_forex_confidence if is_forex else asian_crypto_confidence
        else:
            session_quality = "closed"
            base_confidence = hold_confidence

        indicators["session_quality"] = session_quality

        # Generate signal based on EMA direction
        if ema_direction == "rising":
            confidence = base_confidence
            if is_asian and is_crypto:
                confidence *= asian_crypto_penalty

            if is_overlap:
                session_desc = "overlap"
            elif is_london:
                session_desc = "London"
            elif is_ny:
                session_desc = "NY"
            elif is_asian:
                session_desc = "Asian"
            else:
                session_desc = "off-hours"

            asian_note = " Lower liquidity — reduced confidence." if (is_forex and is_asian) else ""

            return {
                "model": self.name,
                "vote": "BUY",
                "confidence": round(confidence, 2),
                "reasoning": f"{session_desc} session active with {session_quality} conditions. EMA rising confirms bullish bias.{asian_note}",
                "indicators": indicators
            }

        elif ema_direction == "falling":
            confidence = base_confidence
            if is_asian and is_crypto:
                confidence *= asian_crypto_penalty

            if is_overlap:
                session_desc = "overlap"
            elif is_london:
                session_desc = "London"
            elif is_ny:
                session_desc = "NY"
            elif is_asian:
                session_desc = "Asian"
            else:
                session_desc = "off-hours"

            asian_note = " Lower liquidity — reduced confidence." if (is_forex and is_asian) else ""

            return {
                "model": self.name,
                "vote": "SELL",
                "confidence": round(confidence, 2),
                "reasoning": f"{session_desc} session active with {session_quality} conditions. EMA falling confirms bearish bias.{asian_note}",
                "indicators": indicators
            }

        # Flat EMA
        return {
            "model": self.name,
            "vote": "HOLD",
            "confidence": hold_confidence,
            "reasoning": f"Session conditions {session_quality} but flat EMA — no directional bias.",
            "indicators": indicators
        }

    def _get_ema_direction(self, candles: np.ndarray) -> str:
        """Get EMA direction from H1 candles."""
        min_bars = self.p("min_bars", 30)
        ema_period = self.p("ema_period", 20)
        ema_slope_window = self.p("ema_slope_window", 5)
        slope_threshold_pct = self.p("slope_threshold_pct", 0.0001)

        if candles is None or len(candles) < min_bars:
            return "flat"

        closes = candles[:, 4] if candles.shape[1] > 4 else None
        if closes is None or len(closes) < min_bars:
            return "flat"

        ema_20 = ema(closes, ema_period)
        if len(ema_20) < ema_slope_window * 2:
            return "flat"

        # Compare recent EMA values
        ema_recent = ema_20[-ema_slope_window:]
        ema_change = ema_recent[-1] - ema_recent[0]

        threshold = ema_recent[-1] * slope_threshold_pct

        if ema_change > threshold:
            return "rising"
        elif ema_change < -threshold:
            return "falling"
        return "flat"
