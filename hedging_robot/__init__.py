"""
Hedging Grid Robot - Bitget Futures uchun Grid Hedging strategiyasi

HEMA platformasi bilan integratsiya qilingan
"""

__version__ = "1.0.0"
__author__ = "Aliasqar Islomov"

from .config import RobotConfig, APIConfig, TradingConfig, GridConfig, EntryConfig, ProfitConfig
from .robot import HedgingRobot, RobotState
from .strategy import HedgingStrategy, HedgingPosition
from .api_client import BitgetClient, BitgetAPIError
from .webhook_client import WebhookClient, WebhookConfig

__all__ = [
    "RobotConfig",
    "APIConfig",
    "TradingConfig",
    "GridConfig",
    "EntryConfig",
    "ProfitConfig",
    "HedgingRobot",
    "RobotState",
    "HedgingStrategy",
    "HedgingPosition",
    "BitgetClient",
    "BitgetAPIError",
    "WebhookClient",
    "WebhookConfig",
]
