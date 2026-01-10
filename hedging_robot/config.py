"""
Hedging Grid Robot - Konfiguratsiya

Barcha sozlamalar dataclass sifatida
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               ENV LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _load_env():
    """Load .env file"""
    try:
        from dotenv import load_dotenv

        # Try multiple possible locations
        env_paths = [
            Path(".env"),
            Path(__file__).parent / ".env",
            Path(__file__).parent.parent / ".env",
        ]

        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                logger.debug(f"Loaded .env from: {env_path}")
                return

    except ImportError:
        pass


# Load on import
_load_env()


def _get_env(key: str, default: str = "") -> str:
    """Get environment variable"""
    return os.getenv(key, default)


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable"""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _get_env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_env_float(key: str, default: float = 0.0) -> float:
    """Get float environment variable"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


# ═══════════════════════════════════════════════════════════════════════════════
#                               ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class Timeframe(Enum):
    """Timeframe enumeration"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"


# ═══════════════════════════════════════════════════════════════════════════════
#                               CONFIG CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class APIConfig:
    """Bitget API konfiguratsiyasi"""

    DEMO_MODE: bool = field(default_factory=lambda: _get_env_bool("DEMO_MODE", True))
    API_KEY: str = field(default_factory=lambda: _get_env("BITGET_API_KEY", ""))
    SECRET_KEY: str = field(default_factory=lambda: _get_env("BITGET_SECRET_KEY", ""))
    PASSPHRASE: str = field(default_factory=lambda: _get_env("BITGET_PASSPHRASE", ""))

    # URLs
    BASE_URL: str = field(default="")
    WS_PUBLIC_URL: str = field(default="")
    WS_PRIVATE_URL: str = field(default="")

    # Request settings
    TIMEOUT: int = field(default_factory=lambda: _get_env_int("API_TIMEOUT", 30))
    MAX_RETRIES: int = field(default_factory=lambda: _get_env_int("API_MAX_RETRIES", 3))

    def __post_init__(self):
        """Set URLs based on demo mode"""
        if self.DEMO_MODE:
            self.BASE_URL = "https://api.bitget.com"
            self.WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
            self.WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private"
        else:
            self.BASE_URL = "https://api.bitget.com"
            self.WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
            self.WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private"

    def is_configured(self) -> bool:
        """Check if API credentials are configured"""
        return bool(self.API_KEY and self.SECRET_KEY and self.PASSPHRASE)

    def mask_key(self, key: str) -> str:
        """Mask API key for logging"""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


@dataclass
class TradingConfig:
    """Trading sozlamalari"""

    SYMBOL: str = field(default_factory=lambda: _get_env("TRADING_SYMBOL", "BTCUSDT"))
    PRODUCT_TYPE: str = "USDT-FUTURES"
    MARGIN_MODE: str = "crossed"
    MARGIN_COIN: str = "USDT"
    LEVERAGE: int = field(default_factory=lambda: _get_env_int("LEVERAGE", 10))


@dataclass
class GridConfig:
    """Grid trading sozlamalari"""

    # Martingale multiplier (0 = fixed lot, >0 = martingale)
    MULTIPLIER: float = field(default_factory=lambda: _get_env_float("MULTIPLIER", 1.5))

    # Grid Level 1
    SPACE_PERCENT: float = field(default_factory=lambda: _get_env_float("SPACE_PERCENT", 0.5))
    SPACE_ORDERS: int = field(default_factory=lambda: _get_env_int("SPACE_ORDERS", 5))
    SPACE_LOTS: float = field(default_factory=lambda: _get_env_float("SPACE_LOTS", 0.01))

    # Grid Level 2
    SPACE1_PERCENT: float = field(default_factory=lambda: _get_env_float("SPACE1_PERCENT", 1.5))
    SPACE1_ORDERS: int = field(default_factory=lambda: _get_env_int("SPACE1_ORDERS", 1))
    SPACE1_LOTS: float = field(default_factory=lambda: _get_env_float("SPACE1_LOTS", 0.02))

    # Grid Level 3
    SPACE2_PERCENT: float = field(default_factory=lambda: _get_env_float("SPACE2_PERCENT", 3.0))
    SPACE2_ORDERS: int = field(default_factory=lambda: _get_env_int("SPACE2_ORDERS", 1))
    SPACE2_LOTS: float = field(default_factory=lambda: _get_env_float("SPACE2_LOTS", 0.03))

    # Grid Level 4
    SPACE3_PERCENT: float = field(default_factory=lambda: _get_env_float("SPACE3_PERCENT", 5.0))
    SPACE3_ORDERS: int = field(default_factory=lambda: _get_env_int("SPACE3_ORDERS", 99))
    SPACE3_LOTS: float = field(default_factory=lambda: _get_env_float("SPACE3_LOTS", 0.09))

    def get_max_orders(self) -> int:
        """Get total max orders for one side"""
        return self.SPACE_ORDERS + self.SPACE1_ORDERS + self.SPACE2_ORDERS + self.SPACE3_ORDERS


@dataclass
class EntryConfig:
    """Entry signal sozlamalari"""

    # SMA/Parabolic SAR entry
    USE_SMA_SAR: bool = field(default_factory=lambda: _get_env_bool("USE_SMA_SAR", True))
    SMA_PERIOD: int = field(default_factory=lambda: _get_env_int("SMA_PERIOD", 7))
    SAR_AF: float = field(default_factory=lambda: _get_env_float("SAR_AF", 0.1))
    SAR_MAX: float = field(default_factory=lambda: _get_env_float("SAR_MAX", 0.8))
    REVERSE_ORDER: bool = field(default_factory=lambda: _get_env_bool("REVERSE_ORDER", False))

    # CCI entry (0 = disabled)
    CCI_PERIOD: int = field(default_factory=lambda: _get_env_int("CCI_PERIOD", 0))
    CCI_MAX: float = field(default_factory=lambda: _get_env_float("CCI_MAX", 100.0))
    CCI_MIN: float = field(default_factory=lambda: _get_env_float("CCI_MIN", -100.0))

    # Timeframe
    TIMEFRAME: str = field(default_factory=lambda: _get_env("TIMEFRAME", "1H"))


@dataclass
class ProfitConfig:
    """Profit/loss sozlamalari"""

    # Single order profit (USDT)
    SINGLE_ORDER_PROFIT: float = field(default_factory=lambda: _get_env_float("SINGLE_ORDER_PROFIT", 3.0))

    # Pair (buy+sell) global profit (USDT)
    PAIR_GLOBAL_PROFIT: float = field(default_factory=lambda: _get_env_float("PAIR_GLOBAL_PROFIT", 1.0))

    # Global profit target (USDT, 0 = disabled)
    GLOBAL_PROFIT: float = field(default_factory=lambda: _get_env_float("GLOBAL_PROFIT", 0.0))

    # Maximum loss (USDT, 0 = disabled)
    MAX_LOSS: float = field(default_factory=lambda: _get_env_float("MAX_LOSS", 0.0))

    # Trades per day limit
    TRADES_PER_DAY: int = field(default_factory=lambda: _get_env_int("TRADES_PER_DAY", 99))


@dataclass
class TimeConfig:
    """Vaqt filtri sozlamalari"""

    START_HOUR: int = field(default_factory=lambda: _get_env_int("START_HOUR", 0))
    START_MINUTE: int = field(default_factory=lambda: _get_env_int("START_MINUTE", 0))
    FINISH_HOUR: int = field(default_factory=lambda: _get_env_int("FINISH_HOUR", 23))
    FINISH_MINUTE: int = field(default_factory=lambda: _get_env_int("FINISH_MINUTE", 59))

    def is_24h(self) -> bool:
        """Check if 24h trading enabled"""
        return (self.START_HOUR == 0 and self.START_MINUTE == 0 and
                self.FINISH_HOUR == 23 and self.FINISH_MINUTE >= 59)


@dataclass
class MoneyConfig:
    """Money management sozlamalari"""

    # Base lot size
    BASE_LOT: float = field(default_factory=lambda: _get_env_float("BASE_LOT", 0.01))

    # Lot limits
    MIN_LOT: float = field(default_factory=lambda: _get_env_float("MIN_LOT", 0.001))
    MAX_LOT: float = field(default_factory=lambda: _get_env_float("MAX_LOT", 50.0))

    # Money management
    USE_MM: bool = field(default_factory=lambda: _get_env_bool("USE_MM", False))
    RISK_PERCENT: float = field(default_factory=lambda: _get_env_float("RISK_PERCENT", 2.0))


@dataclass
class RobotConfig:
    """Asosiy robot konfiguratsiyasi"""

    # Sub-configs
    api: APIConfig = field(default_factory=APIConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)
    profit: ProfitConfig = field(default_factory=ProfitConfig)
    time: TimeConfig = field(default_factory=TimeConfig)
    money: MoneyConfig = field(default_factory=MoneyConfig)

    # Robot info
    ROBOT_NAME: str = field(default_factory=lambda: _get_env("BOT_NAME", "Hedging Grid Robot"))
    VERSION: str = field(default_factory=lambda: _get_env("BOT_VERSION", "1.0.0"))

    # Runtime settings
    DEBUG: bool = field(default_factory=lambda: _get_env_bool("DEBUG", False))
    TICK_INTERVAL: float = field(default_factory=lambda: _get_env_float("TICK_INTERVAL", 1.0))
    OPEN_ON_NEW_CANDLE: bool = field(default_factory=lambda: _get_env_bool("OPEN_ON_NEW_CANDLE", True))

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []

        # API validation
        if not self.api.is_configured():
            errors.append("API credentials not configured")

        # Trading validation
        if self.trading.LEVERAGE < 1 or self.trading.LEVERAGE > 125:
            errors.append(f"Invalid leverage: {self.trading.LEVERAGE} (must be 1-125)")

        # Grid validation
        if self.grid.SPACE_PERCENT <= 0:
            errors.append("SPACE_PERCENT must be positive")
        if self.grid.SPACE_ORDERS < 1:
            errors.append("SPACE_ORDERS must be at least 1")

        # Entry validation
        if not self.entry.USE_SMA_SAR and self.entry.CCI_PERIOD <= 0:
            errors.append("At least one entry method must be enabled (SMA/SAR or CCI)")

        # Money validation
        if self.money.BASE_LOT < self.money.MIN_LOT:
            errors.append(f"BASE_LOT ({self.money.BASE_LOT}) < MIN_LOT ({self.money.MIN_LOT})")

        return errors

    def print_config(self):
        """Print configuration summary"""
        print("\n" + "=" * 60)
        print(f"  {self.ROBOT_NAME} v{self.VERSION}")
        print("=" * 60)
        print(f"  Symbol:     {self.trading.SYMBOL}")
        print(f"  Leverage:   {self.trading.LEVERAGE}x")
        print(f"  Demo Mode:  {self.api.DEMO_MODE}")
        print(f"  Timeframe:  {self.entry.TIMEFRAME}")
        print("-" * 60)
        print("  GRID SETTINGS:")
        print(f"    Multiplier: {self.grid.MULTIPLIER}")
        print(f"    Level 1: {self.grid.SPACE_PERCENT}% / {self.grid.SPACE_ORDERS} orders")
        print(f"    Level 2: {self.grid.SPACE1_PERCENT}% / {self.grid.SPACE1_ORDERS} orders")
        print(f"    Level 3: {self.grid.SPACE2_PERCENT}% / {self.grid.SPACE2_ORDERS} orders")
        print(f"    Level 4: {self.grid.SPACE3_PERCENT}% / {self.grid.SPACE3_ORDERS} orders")
        print("-" * 60)
        print("  ENTRY SETTINGS:")
        print(f"    SMA/SAR: {self.entry.USE_SMA_SAR}")
        if self.entry.USE_SMA_SAR:
            print(f"      SMA Period: {self.entry.SMA_PERIOD}")
            print(f"      SAR AF: {self.entry.SAR_AF}, Max: {self.entry.SAR_MAX}")
        print(f"    CCI: {self.entry.CCI_PERIOD > 0}")
        if self.entry.CCI_PERIOD > 0:
            print(f"      Period: {self.entry.CCI_PERIOD}")
            print(f"      Range: {self.entry.CCI_MIN} to {self.entry.CCI_MAX}")
        print("-" * 60)
        print("  PROFIT SETTINGS:")
        print(f"    Single Order: ${self.profit.SINGLE_ORDER_PROFIT}")
        print(f"    Pair Global:  ${self.profit.PAIR_GLOBAL_PROFIT}")
        print(f"    Global Target: ${self.profit.GLOBAL_PROFIT}")
        print(f"    Max Loss:      ${self.profit.MAX_LOSS}")
        print("=" * 60 + "\n")
