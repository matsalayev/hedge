"""
Hedging Grid Robot - Texnik Indikatorlar

SMA, Parabolic SAR, CCI indikatorlari
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               CANDLE DATA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Candle:
    """OHLCV candle ma'lumotlari"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_bitget(cls, data: List) -> 'Candle':
        """
        Bitget API formatidan Candle yaratish

        Bitget format: [timestamp, open, high, low, close, volume, ...]
        """
        return cls(
            timestamp=int(data[0]),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]) if len(data) > 5 else 0.0
        )

    def get_typical_price(self) -> float:
        """Typical price (HLC/3)"""
        return (self.high + self.low + self.close) / 3

    def get_weighted_price(self) -> float:
        """Weighted price (HLCC/4)"""
        return (self.high + self.low + self.close + self.close) / 4


# ═══════════════════════════════════════════════════════════════════════════════
#                               SMA INDICATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SMAIndicator:
    """
    Simple Moving Average (SMA) / Linear Weighted Moving Average (LWMA)

    MQL4 dan: iMA(NULL, 0, 7, 0, MODE_LWMA, PRICE_WEIGHTED, 0)
    """

    def __init__(self, period: int = 7, ma_type: str = 'lwma'):
        """
        Args:
            period: MA period
            ma_type: 'sma' yoki 'lwma' (Linear Weighted)
        """
        self.period = period
        self.ma_type = ma_type.lower()
        self._last_value: float = 0.0

    @property
    def value(self) -> float:
        """Oxirgi hisoblangan qiymat"""
        return self._last_value

    def calculate(self, candles: List[Candle]) -> float:
        """
        MA ni hisoblash

        Args:
            candles: Candle ro'yxati (eng yangisi oxirida)

        Returns:
            MA qiymati
        """
        if len(candles) < self.period:
            logger.warning(f"SMA: Not enough candles ({len(candles)} < {self.period})")
            return 0.0

        # Oxirgi N ta candle
        recent = candles[-self.period:]

        if self.ma_type == 'lwma':
            # Linear Weighted MA
            weighted_sum = 0.0
            weight_sum = 0

            for i, candle in enumerate(recent):
                weight = i + 1  # 1, 2, 3, ..., period
                price = candle.get_weighted_price()
                weighted_sum += price * weight
                weight_sum += weight

            self._last_value = weighted_sum / weight_sum if weight_sum > 0 else 0.0
        else:
            # Simple MA
            prices = [c.get_weighted_price() for c in recent]
            self._last_value = sum(prices) / len(prices)

        return self._last_value


# ═══════════════════════════════════════════════════════════════════════════════
#                           PARABOLIC SAR INDICATOR
# ═══════════════════════════════════════════════════════════════════════════════

class ParabolicSARIndicator:
    """
    Parabolic SAR (Stop and Reverse)

    MQL4 dan: iSAR(NULL, 0, 0.1, 0.8, 0)
    """

    def __init__(self, af_start: float = 0.1, af_max: float = 0.8):
        """
        Args:
            af_start: Acceleration Factor boshlang'ich qiymati
            af_max: AF maksimal qiymati
        """
        self.af_start = af_start
        self.af_max = af_max

        # Internal state
        self._is_long: bool = True
        self._sar: float = 0.0
        self._ep: float = 0.0  # Extreme Point
        self._af: float = af_start
        self._initialized: bool = False
        self._last_value: float = 0.0

    @property
    def value(self) -> float:
        """Oxirgi SAR qiymati"""
        return self._last_value

    def reset(self):
        """Reset indicator state"""
        self._is_long = True
        self._sar = 0.0
        self._ep = 0.0
        self._af = self.af_start
        self._initialized = False
        self._last_value = 0.0

    def calculate(self, candles: List[Candle]) -> float:
        """
        Parabolic SAR ni hisoblash

        Args:
            candles: Candle ro'yxati (eng yangisi oxirida)

        Returns:
            SAR qiymati
        """
        if len(candles) < 2:
            return 0.0

        # Initialize on first call
        if not self._initialized:
            self._initialize(candles)
            return self._last_value

        # Current candle
        current = candles[-1]
        prev = candles[-2]

        # Calculate new SAR
        new_sar = self._sar + self._af * (self._ep - self._sar)

        if self._is_long:
            # Long trend
            # SAR can't be above previous two lows
            new_sar = min(new_sar, prev.low)
            if len(candles) >= 3:
                new_sar = min(new_sar, candles[-3].low)

            # Check for reversal
            if current.low < new_sar:
                # Reverse to short
                self._is_long = False
                new_sar = self._ep
                self._ep = current.low
                self._af = self.af_start
            else:
                # Update EP if new high
                if current.high > self._ep:
                    self._ep = current.high
                    self._af = min(self._af + self.af_start, self.af_max)
        else:
            # Short trend
            # SAR can't be below previous two highs
            new_sar = max(new_sar, prev.high)
            if len(candles) >= 3:
                new_sar = max(new_sar, candles[-3].high)

            # Check for reversal
            if current.high > new_sar:
                # Reverse to long
                self._is_long = True
                new_sar = self._ep
                self._ep = current.high
                self._af = self.af_start
            else:
                # Update EP if new low
                if current.low < self._ep:
                    self._ep = current.low
                    self._af = min(self._af + self.af_start, self.af_max)

        self._sar = new_sar
        self._last_value = new_sar
        return new_sar

    def _initialize(self, candles: List[Candle]):
        """Initialize SAR with first few candles"""
        if len(candles) < 5:
            self._last_value = candles[-1].low
            return

        # Find initial trend by comparing first and last prices
        first_few = candles[:5]
        if first_few[-1].close > first_few[0].close:
            # Uptrend
            self._is_long = True
            self._sar = min(c.low for c in first_few)
            self._ep = max(c.high for c in first_few)
        else:
            # Downtrend
            self._is_long = False
            self._sar = max(c.high for c in first_few)
            self._ep = min(c.low for c in first_few)

        self._af = self.af_start
        self._initialized = True
        self._last_value = self._sar


# ═══════════════════════════════════════════════════════════════════════════════
#                               CCI INDICATOR
# ═══════════════════════════════════════════════════════════════════════════════

class CCIIndicator:
    """
    Commodity Channel Index (CCI)

    MQL4 dan: iCCI(Symbol(), 0, cciperiod, PRICE_TYPICAL, 0)
    """

    def __init__(self, period: int = 14):
        """
        Args:
            period: CCI period
        """
        self.period = period
        self._last_value: float = 0.0
        self._history: List[float] = []

    @property
    def value(self) -> float:
        """Oxirgi CCI qiymati"""
        return self._last_value

    @property
    def previous(self) -> float:
        """Oldingi CCI qiymati"""
        if len(self._history) >= 2:
            return self._history[-2]
        return 0.0

    def calculate(self, candles: List[Candle]) -> float:
        """
        CCI ni hisoblash

        CCI = (TP - SMA(TP)) / (0.015 * Mean Deviation)

        Args:
            candles: Candle ro'yxati

        Returns:
            CCI qiymati
        """
        if len(candles) < self.period:
            logger.warning(f"CCI: Not enough candles ({len(candles)} < {self.period})")
            return 0.0

        # Oxirgi N ta typical price
        recent = candles[-self.period:]
        typical_prices = [c.get_typical_price() for c in recent]

        # SMA of typical prices
        sma = sum(typical_prices) / len(typical_prices)

        # Mean Deviation
        mean_dev = sum(abs(tp - sma) for tp in typical_prices) / len(typical_prices)

        # CCI
        if mean_dev == 0:
            cci = 0.0
        else:
            current_tp = typical_prices[-1]
            cci = (current_tp - sma) / (0.015 * mean_dev)

        self._last_value = cci

        # Keep history
        self._history.append(cci)
        if len(self._history) > 100:
            self._history = self._history[-100:]

        return cci

    def is_above(self, level: float) -> bool:
        """CCI level ustidami?"""
        return self._last_value > level

    def is_below(self, level: float) -> bool:
        """CCI level ostidami?"""
        return self._last_value < level

    def crossed_above(self, level: float) -> bool:
        """CCI level dan yuqoriga o'tdimi?"""
        if len(self._history) < 2:
            return False
        return self._history[-2] <= level < self._history[-1]

    def crossed_below(self, level: float) -> bool:
        """CCI level dan pastga o'tdimi?"""
        if len(self._history) < 2:
            return False
        return self._history[-2] >= level > self._history[-1]
