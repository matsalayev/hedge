"""
Hedging Grid Robot - Session Manager

Ko'p foydalanuvchi sessiyalarini boshqarish
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import RobotConfig, APIConfig, TradingConfig, GridConfig, EntryConfig, ProfitConfig, TimeConfig, MoneyConfig
from .robot import HedgingRobot, RobotState
from .webhook_client import WebhookClient, WebhookConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               SESSION STATUS
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStatus(Enum):
    """Session holatlari"""
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════════════════════════
#                               USER SESSION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UserSession:
    """Foydalanuvchi sessiyasi"""

    # User info
    user_id: str
    user_bot_id: str
    status: SessionStatus = SessionStatus.REGISTERED

    # Exchange credentials
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    is_demo: bool = True

    # Trading settings
    trading_pair: str = "BTCUSDT"
    leverage: int = 10

    # Grid settings
    multiplier: float = 1.5
    space_percent: float = 0.5
    space_orders: int = 5
    space1_percent: float = 1.5
    space1_orders: int = 1
    space2_percent: float = 3.0
    space2_orders: int = 1
    space3_percent: float = 5.0
    space3_orders: int = 99

    # Entry settings
    use_sma_sar: bool = True
    sma_period: int = 7
    sar_af: float = 0.1
    sar_max: float = 0.8
    reverse_order: bool = False
    cci_period: int = 0
    cci_max: float = 100.0
    cci_min: float = -100.0
    timeframe: str = "1H"

    # Profit settings
    single_order_profit: float = 3.0
    pair_global_profit: float = 1.0
    global_profit: float = 0.0
    max_loss: float = 0.0
    trades_per_day: int = 99

    # Money settings
    base_lot: float = 0.01
    min_lot: float = 0.001
    max_lot: float = 50.0

    # Webhook
    webhook_url: str = ""
    webhook_secret: str = ""

    # Runtime (not serialized)
    robot: Optional[HedgingRobot] = field(default=None, repr=False)
    webhook_client: Optional[WebhookClient] = field(default=None, repr=False)
    task: Optional[asyncio.Task] = field(default=None, repr=False)

    # Timestamps
    registered_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    # Stats
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary (without sensitive data)"""
        return {
            "user_id": self.user_id,
            "user_bot_id": self.user_bot_id,
            "status": self.status.value,
            "trading_pair": self.trading_pair,
            "leverage": self.leverage,
            "is_demo": self.is_demo,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "total_pnl": self.total_pnl,
            "settings": {
                "multiplier": self.multiplier,
                "space_percent": self.space_percent,
                "space_orders": self.space_orders,
                "single_order_profit": self.single_order_profit,
                "pair_global_profit": self.pair_global_profit,
                "base_lot": self.base_lot,
                "timeframe": self.timeframe
            }
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                           ROBOT WITH WEBHOOK
# ═══════════════════════════════════════════════════════════════════════════════

class HedgingRobotWithWebhook(HedgingRobot):
    """Webhook qo'llab-quvvatlovchi robot"""

    def __init__(self, config: RobotConfig, webhook_client: WebhookClient, user_bot_id: str):
        super().__init__(config)
        self.webhook_client = webhook_client
        self.user_bot_id = user_bot_id

    async def _tick(self):
        """Tick with webhook status update"""
        await super()._tick()

        # Send status update every 5 ticks
        if self.tick_count % 5 == 0 and self.webhook_client:
            await self._send_status_update()

    async def _send_status_update(self):
        """Send status update to HEMA"""
        if not self.strategy:
            return

        try:
            settings = {
                "leverage": self.config.trading.LEVERAGE,
                "multiplier": self.config.grid.MULTIPLIER,
                "space_percent": self.config.grid.SPACE_PERCENT,
                "single_order_profit": self.config.profit.SINGLE_ORDER_PROFIT,
                "pair_global_profit": self.config.profit.PAIR_GLOBAL_PROFIT,
                "base_lot": self.config.money.BASE_LOT,
                "timeframe": self.config.entry.TIMEFRAME,
                "use_sma_sar": self.config.entry.USE_SMA_SAR,
                "cci_period": self.config.entry.CCI_PERIOD
            }

            runtime = {
                "tick": self.tick_count,
                "uptime": int((datetime.utcnow() - self.start_time).total_seconds()) if self.start_time else 0,
                "startedAt": self.start_time.isoformat() + "Z" if self.start_time else ""
            }

            await self.webhook_client.send_status_update(
                user_bot_id=self.user_bot_id,
                symbol=self.config.trading.SYMBOL,
                current_price=self.current_price,
                sma_value=self.strategy.sma.value,
                sar_value=self.strategy.sar.value,
                cci_value=self.strategy.cci.value if self.strategy.cci else 0,
                signal="BUY" if self.strategy.fire_buy else ("SELL" if self.strategy.fire_sell else "NONE"),
                balance=self.balance,
                buy_positions=[p.to_dict() for p in self.strategy.buy_positions],
                sell_positions=[p.to_dict() for p in self.strategy.sell_positions],
                stats=self.strategy.get_stats(),
                settings=settings,
                runtime=runtime
            )

        except Exception as e:
            logger.error(f"Failed to send status update: {e}")

    async def _open_buy(self, lot: float, level: int):
        """Open buy with webhook"""
        await super()._open_buy(lot, level)

        if self.webhook_client and self.strategy.buy_positions:
            pos = self.strategy.buy_positions[-1]
            await self.webhook_client.send_trade_opened(
                user_bot_id=self.user_bot_id,
                symbol=self.config.trading.SYMBOL,
                side="BUY",
                price=pos.entry_price,
                quantity=pos.lot,
                order_id=pos.id,
                grid_level=level
            )

    async def _open_sell(self, lot: float, level: int):
        """Open sell with webhook"""
        await super()._open_sell(lot, level)

        if self.webhook_client and self.strategy.sell_positions:
            pos = self.strategy.sell_positions[-1]
            await self.webhook_client.send_trade_opened(
                user_bot_id=self.user_bot_id,
                symbol=self.config.trading.SYMBOL,
                side="SELL",
                price=pos.entry_price,
                quantity=pos.lot,
                order_id=pos.id,
                grid_level=level
            )

    async def _close_buy_positions(self, reason: str = "PROFIT_TARGET"):
        """Close buy positions with webhook"""
        if not self.strategy.buy_positions:
            return

        avg_price = self.strategy.get_average_buy_price()
        count = len(self.strategy.buy_positions)
        # Calculate total lot BEFORE closing (positions will be cleared)
        total_lot = sum(p.lot for p in self.strategy.buy_positions)
        positions_before = len(self.strategy.buy_positions)

        await super()._close_buy_positions()

        # Only send webhook if positions were actually closed (not cleared due to error)
        positions_after = len(self.strategy.buy_positions)
        if positions_after < positions_before and self.webhook_client:
            # PnL = price_diff * total_lot * leverage (not count!)
            pnl = (self.current_price - avg_price) * total_lot * self.config.trading.LEVERAGE
            await self.webhook_client.send_positions_closed(
                user_bot_id=self.user_bot_id,
                symbol=self.config.trading.SYMBOL,
                side="BUY",
                positions_count=count,
                total_quantity=total_lot,
                total_pnl=pnl,
                avg_entry_price=avg_price,
                exit_price=self.current_price,
                reason=reason
            )

    async def _close_sell_positions(self, reason: str = "PROFIT_TARGET"):
        """Close sell positions with webhook"""
        if not self.strategy.sell_positions:
            return

        avg_price = self.strategy.get_average_sell_price()
        count = len(self.strategy.sell_positions)
        # Calculate total lot BEFORE closing (positions will be cleared)
        total_lot = sum(p.lot for p in self.strategy.sell_positions)
        positions_before = len(self.strategy.sell_positions)

        await super()._close_sell_positions()

        # Only send webhook if positions were actually closed (not cleared due to error)
        positions_after = len(self.strategy.sell_positions)
        if positions_after < positions_before and self.webhook_client:
            # PnL = price_diff * total_lot * leverage (not count!)
            pnl = (avg_price - self.current_price) * total_lot * self.config.trading.LEVERAGE
            await self.webhook_client.send_positions_closed(
                user_bot_id=self.user_bot_id,
                symbol=self.config.trading.SYMBOL,
                side="SELL",
                positions_count=count,
                total_quantity=total_lot,
                total_pnl=pnl,
                avg_entry_price=avg_price,
                exit_price=self.current_price,
                reason=reason
            )

    async def close_all_positions_manually(self, reason: str = "MANUAL_CLOSE"):
        """Manually close all positions - called from API endpoint"""
        logger.info(f"[MANUAL_CLOSE] Closing all positions for {self.user_bot_id}")
        await self._close_buy_positions(reason=reason)
        await self._close_sell_positions(reason=reason)
        logger.info(f"[MANUAL_CLOSE] All positions closed for {self.user_bot_id}")


# ═══════════════════════════════════════════════════════════════════════════════
#                           SESSION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """
    Ko'p foydalanuvchi sessiyalarini boshqaruvchi

    Singleton pattern
    """

    _instance: Optional['SessionManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, UserSession] = {}
            cls._instance._lock = asyncio.Lock()
            cls._instance._last_cleanup = datetime.utcnow()
        return cls._instance

    async def cleanup_old_sessions(self, max_age_hours: int = 24):
        """
        N9 fix - Eski to'xtatilgan sessiyalarni tozalash

        Args:
            max_age_hours: Sessiya yoshi chegarasi (soat)
        """
        async with self._lock:
            now = datetime.utcnow()

            # Faqat har soatda bir marta tozalash
            if (now - self._last_cleanup).total_seconds() < 3600:
                return

            self._last_cleanup = now
            to_remove = []

            for user_id, session in self._sessions.items():
                # Faqat STOPPED yoki ERROR sessiyalarni tekshirish
                if session.status not in (SessionStatus.STOPPED, SessionStatus.ERROR):
                    continue

                # Yoshi tekshirish
                if session.stopped_at:
                    age_hours = (now - session.stopped_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(user_id)

            # Eski sessiyalarni o'chirish
            for user_id in to_remove:
                del self._sessions[user_id]
                logger.info(f"Cleaned up old session: {user_id}")

            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old sessions")

    @property
    def active_sessions(self) -> int:
        """Faol sessiyalar soni"""
        return sum(1 for s in self._sessions.values() if s.status == SessionStatus.RUNNING)

    @property
    def total_sessions(self) -> int:
        """Jami sessiyalar soni"""
        return len(self._sessions)

    async def register_user(
        self,
        user_id: str,
        user_bot_id: str,
        exchange: Dict[str, Any],
        settings: Dict[str, Any],
        webhook_url: str,
        webhook_secret: str
    ) -> UserSession:
        """
        Yangi foydalanuvchini ro'yxatdan o'tkazish

        Args:
            user_id: HEMA user ID
            user_bot_id: HEMA UserBot ID
            exchange: Exchange credentials
            settings: Trading settings
            webhook_url: Webhook URL
            webhook_secret: Webhook secret

        Returns:
            UserSession
        """
        async with self._lock:
            # Check if already exists
            if user_id in self._sessions:
                logger.warning(f"User {user_id} already registered, updating...")
                session = self._sessions[user_id]
            else:
                session = UserSession(user_id=user_id, user_bot_id=user_bot_id)

            # Update credentials
            session.api_key = exchange.get("apiKey", "")
            session.api_secret = exchange.get("apiSecret", "")
            session.passphrase = exchange.get("passphrase", "")
            session.is_demo = exchange.get("isDemo", True)

            # Update trading settings
            session.trading_pair = settings.get("tradingPair", "BTCUSDT")
            session.leverage = settings.get("leverage", 10)

            # Update custom settings
            custom = settings.get("customSettings", {})

            # Grid settings
            session.multiplier = custom.get("multiplier", 1.5)
            session.space_percent = custom.get("spacePercent", 0.5)
            session.space_orders = custom.get("spaceOrders", 5)
            session.space1_percent = custom.get("space1Percent", 1.5)
            session.space1_orders = custom.get("space1Orders", 1)
            session.space2_percent = custom.get("space2Percent", 3.0)
            session.space2_orders = custom.get("space2Orders", 1)
            session.space3_percent = custom.get("space3Percent", 5.0)
            session.space3_orders = custom.get("space3Orders", 99)

            # Entry settings
            session.use_sma_sar = custom.get("useSmaSar", True)
            session.sma_period = custom.get("smaPeriod", 7)
            session.sar_af = custom.get("sarAf", 0.1)
            session.sar_max = custom.get("sarMax", 0.8)
            session.reverse_order = custom.get("reverseOrder", False)
            session.cci_period = custom.get("cciPeriod", 0)
            session.cci_max = custom.get("cciMax", 100.0)
            session.cci_min = custom.get("cciMin", -100.0)
            session.timeframe = custom.get("timeframe", "1H")

            # Profit settings
            session.single_order_profit = custom.get("singleOrderProfit", settings.get("takeProfit", 3.0))
            session.pair_global_profit = custom.get("pairGlobalProfit", 1.0)
            session.global_profit = custom.get("globalProfit", 0.0)
            session.max_loss = custom.get("maxLoss", 0.0)
            session.trades_per_day = custom.get("tradesPerDay", 99)

            # Money settings
            session.base_lot = custom.get("baseLot", settings.get("tradeAmount", 0.01))
            session.min_lot = custom.get("minLot", 0.001)
            session.max_lot = custom.get("maxLot", 50.0)

            # Webhook
            session.webhook_url = webhook_url
            session.webhook_secret = webhook_secret

            session.status = SessionStatus.REGISTERED
            self._sessions[user_id] = session

            logger.info(f"User {user_id} registered for {session.trading_pair}")
            return session

    async def unregister_user(self, user_id: str) -> bool:
        """Foydalanuvchini ro'yxatdan o'chirish"""
        async with self._lock:
            if user_id not in self._sessions:
                return False

            session = self._sessions[user_id]

            # Stop if running
            if session.status == SessionStatus.RUNNING:
                await self.stop_trading(user_id)

            del self._sessions[user_id]
            logger.info(f"User {user_id} unregistered")
            return True

    async def start_trading(self, user_id: str) -> UserSession:
        """Savdoni boshlash"""
        session = self.get_session(user_id)
        if not session:
            raise ValueError(f"User {user_id} not found")

        if session.status == SessionStatus.RUNNING:
            return session

        session.status = SessionStatus.STARTING

        # Create config
        config = self._create_robot_config(session)

        # Create webhook client
        webhook_client = None
        if session.webhook_url:
            webhook_config = WebhookConfig(
                url=session.webhook_url,
                secret=session.webhook_secret
            )
            webhook_client = WebhookClient(webhook_config)
            webhook_client.set_user_id(user_id)
            await webhook_client.start()
            session.webhook_client = webhook_client

        # Create robot
        robot = HedgingRobotWithWebhook(config, webhook_client, session.user_bot_id)
        session.robot = robot

        # Start in background
        session.task = asyncio.create_task(self._run_robot(session))
        session.started_at = datetime.utcnow()
        session.status = SessionStatus.RUNNING

        # Send status changed webhook
        if webhook_client:
            await webhook_client.send_status_changed(
                session.user_bot_id, "running", "Trading started"
            )

        logger.info(f"Started trading for user {user_id}")
        return session

    async def stop_trading(self, user_id: str) -> UserSession:
        """Savdoni to'xtatish"""
        session = self.get_session(user_id)
        if not session:
            raise ValueError(f"User {user_id} not found")

        if session.status != SessionStatus.RUNNING:
            return session

        session.status = SessionStatus.STOPPING

        # Stop robot
        if session.robot:
            await session.robot.stop()

            # Update stats
            if session.robot.strategy:
                stats = session.robot.strategy.get_stats()
                session.total_trades = stats.get("total_trades", 0)
                session.winning_trades = stats.get("winning_trades", 0)
                session.total_pnl = stats.get("total_profit", 0.0)

        # Cancel task
        if session.task:
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass

        # Send status changed webhook
        if session.webhook_client:
            await session.webhook_client.send_status_changed(
                session.user_bot_id, "stopped", "Trading stopped"
            )
            await session.webhook_client.stop()

        session.stopped_at = datetime.utcnow()
        session.status = SessionStatus.STOPPED
        session.robot = None
        session.webhook_client = None
        session.task = None

        logger.info(f"Stopped trading for user {user_id}")
        return session

    async def get_status(self, user_id: str) -> Dict:
        """Foydalanuvchi statusini olish"""
        session = self.get_session(user_id)
        if not session:
            raise ValueError(f"User {user_id} not found")

        result = session.to_dict()

        # Add robot status if running
        if session.robot and session.status == SessionStatus.RUNNING:
            result["robot"] = session.robot.get_status()

        return result

    def get_session(self, user_id: str) -> Optional[UserSession]:
        """Sessiyani olish"""
        return self._sessions.get(user_id)

    def _create_robot_config(self, session: UserSession) -> RobotConfig:
        """UserSession dan RobotConfig yaratish"""
        api = APIConfig()
        api.API_KEY = session.api_key
        api.SECRET_KEY = session.api_secret
        api.PASSPHRASE = session.passphrase
        api.DEMO_MODE = session.is_demo
        api.__post_init__()

        trading = TradingConfig()
        trading.SYMBOL = session.trading_pair
        trading.LEVERAGE = session.leverage

        grid = GridConfig()
        grid.MULTIPLIER = session.multiplier
        grid.SPACE_PERCENT = session.space_percent
        grid.SPACE_ORDERS = session.space_orders
        grid.SPACE1_PERCENT = session.space1_percent
        grid.SPACE1_ORDERS = session.space1_orders
        grid.SPACE2_PERCENT = session.space2_percent
        grid.SPACE2_ORDERS = session.space2_orders
        grid.SPACE3_PERCENT = session.space3_percent
        grid.SPACE3_ORDERS = session.space3_orders

        entry = EntryConfig()
        entry.USE_SMA_SAR = session.use_sma_sar
        entry.SMA_PERIOD = session.sma_period
        entry.SAR_AF = session.sar_af
        entry.SAR_MAX = session.sar_max
        entry.REVERSE_ORDER = session.reverse_order
        entry.CCI_PERIOD = session.cci_period
        entry.CCI_MAX = session.cci_max
        entry.CCI_MIN = session.cci_min
        entry.TIMEFRAME = session.timeframe

        profit = ProfitConfig()
        profit.SINGLE_ORDER_PROFIT = session.single_order_profit
        profit.PAIR_GLOBAL_PROFIT = session.pair_global_profit
        profit.GLOBAL_PROFIT = session.global_profit
        profit.MAX_LOSS = session.max_loss
        profit.TRADES_PER_DAY = session.trades_per_day

        money = MoneyConfig()
        money.BASE_LOT = session.base_lot
        money.MIN_LOT = session.min_lot
        money.MAX_LOT = session.max_lot

        return RobotConfig(
            api=api,
            trading=trading,
            grid=grid,
            entry=entry,
            profit=profit,
            time=TimeConfig(),
            money=money
        )

    async def _run_robot(self, session: UserSession):
        """Robot'ni background'da ishlatish"""
        try:
            await session.robot.start()
        except Exception as e:
            logger.error(f"Robot error for user {session.user_id}: {e}")
            session.status = SessionStatus.ERROR


def get_session_manager() -> SessionManager:
    """Session manager singleton olish"""
    return SessionManager()
