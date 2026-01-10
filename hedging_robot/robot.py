"""
Hedging Grid Robot - Asosiy Robot

Main trading loop va state management
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

from .config import RobotConfig
from .api_client import BitgetClient, BitgetAPIError
from .strategy import HedgingStrategy, HedgingPosition
from .indicators import Candle

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               ROBOT STATE
# ═══════════════════════════════════════════════════════════════════════════════

class RobotState(Enum):
    """Robot holatlari"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════════════════════════
#                               HEDGING ROBOT
# ═══════════════════════════════════════════════════════════════════════════════

class HedgingRobot:
    """
    Hedging Grid Trading Robot

    Asosiy trading logic va loop
    """

    def __init__(self, config: RobotConfig):
        """
        Args:
            config: Robot konfiguratsiyasi
        """
        self.config = config
        self.state = RobotState.IDLE
        self.client: Optional[BitgetClient] = None
        self.strategy: Optional[HedgingStrategy] = None

        # Market data
        self.current_price: float = 0.0
        self.balance: float = 0.0
        self.candles: List[Candle] = []

        # Stats
        self.start_time: Optional[datetime] = None
        self.tick_count: int = 0
        self.last_bar_time: int = 0

        # Flags
        self._running: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    #                           LIFECYCLE METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """
        Robotni ishga tayyorlash

        Returns:
            True if successful
        """
        logger.info("Initializing robot...")
        self.state = RobotState.STARTING

        # Validate config
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            self.state = RobotState.ERROR
            return False

        # Create API client
        self.client = BitgetClient(self.config.api)

        try:
            # Test connection
            self.balance = await self.client.get_balance()
            logger.info(f"Connected to Bitget. Balance: ${self.balance:.2f}")

            # Set leverage
            await self.client.set_leverage(
                symbol=self.config.trading.SYMBOL,
                leverage=self.config.trading.LEVERAGE
            )
            logger.info(f"Leverage set to {self.config.trading.LEVERAGE}x")

        except BitgetAPIError as e:
            logger.error(f"API error: {e}")
            self.state = RobotState.ERROR
            return False

        # Create strategy
        self.strategy = HedgingStrategy(self.config)

        # Print config
        self.config.print_config()

        self.state = RobotState.IDLE
        logger.info("Robot initialized successfully")
        return True

    async def start(self):
        """Robotni ishga tushirish"""
        if not self.client or not self.strategy:
            success = await self.initialize()
            if not success:
                return

        self.state = RobotState.RUNNING
        self._running = True
        self.start_time = datetime.utcnow()
        self.tick_count = 0

        logger.info(f"Robot started. Trading {self.config.trading.SYMBOL}")

        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self.config.TICK_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Robot cancelled")
        except KeyboardInterrupt:
            logger.info("Robot interrupted")
        except Exception as e:
            logger.error(f"Robot error: {e}", exc_info=True)
            self.state = RobotState.ERROR
        finally:
            await self.stop()

    async def stop(self):
        """Robotni to'xtatish"""
        if self.state == RobotState.STOPPED:
            return

        logger.info("Stopping robot...")
        self.state = RobotState.STOPPING
        self._running = False

        # Close all positions
        if self.strategy and (self.strategy.buy_positions or self.strategy.sell_positions):
            logger.info("Closing all positions...")
            try:
                await self._close_all_positions()
            except Exception as e:
                logger.error(f"Error closing positions: {e}")

        # Close API client
        if self.client:
            await self.client.close()

        self.state = RobotState.STOPPED
        logger.info("Robot stopped")

    # ─────────────────────────────────────────────────────────────────────────
    #                           MAIN TICK LOOP
    # ─────────────────────────────────────────────────────────────────────────

    async def _tick(self):
        """
        Asosiy trading tick

        Har bir tick da:
        1. Market data yangilanadi
        2. Indikatorlar yangilanadi
        3. Global limitlar tekshiriladi
        4. Profit taking tekshiriladi
        5. Entry signallari tekshiriladi
        6. Grid qo'shimchalar tekshiriladi
        """
        self.tick_count += 1

        try:
            # 1. Update market data
            await self._update_market_data()

            # 2. Check if new bar
            is_new_bar = self._is_new_bar()

            # 3. Update indicators
            self.strategy.update_indicators(self.candles)

            # 4. Check global limits
            should_stop, reason = self.strategy.check_global_limits(
                self.current_price,
                self.config.trading.LEVERAGE
            )
            if should_stop:
                logger.warning(f"Global limit hit: {reason}")
                await self._close_all_positions()
                self.strategy.stop_trading()
                return

            if self.strategy.should_stop_trading():
                return

            # 5. Check profit taking
            await self._check_profit_taking()

            # 6. Check trading time
            if not self._check_trading_time():
                return

            # 7. Check entry signals (only on new bar)
            self.strategy.check_entry_signals(is_new_bar)

            # 8. Open initial orders
            await self._check_initial_orders()

            # 9. Check grid additions
            if not self.config.OPEN_ON_NEW_CANDLE or is_new_bar:
                await self._check_grid_additions()

            # 10. Display status
            if self.tick_count % 10 == 0:  # Every 10 ticks
                self._display_status()

        except BitgetAPIError as e:
            logger.error(f"API error in tick: {e}")
        except Exception as e:
            logger.error(f"Error in tick: {e}", exc_info=True)

    async def _update_market_data(self):
        """Market ma'lumotlarini yangilash"""
        # Get current price
        self.current_price = await self.client.get_price(self.config.trading.SYMBOL)

        # Get candles
        candle_data = await self.client.get_candles(
            symbol=self.config.trading.SYMBOL,
            granularity=self.config.entry.TIMEFRAME,
            limit=100
        )

        self.candles = [Candle.from_bitget(c) for c in candle_data]
        self.candles.sort(key=lambda c: c.timestamp)  # Sort by time

        # Update balance periodically
        if self.tick_count % 30 == 0:
            self.balance = await self.client.get_balance()

    def _is_new_bar(self) -> bool:
        """Yangi sham ochildimi?"""
        if not self.candles:
            return False

        current_time = self.candles[-1].timestamp
        if current_time > self.last_bar_time:
            self.last_bar_time = current_time
            return True
        return False

    def _check_trading_time(self) -> bool:
        """Savdo vaqtidamizmi?"""
        if self.config.time.is_24h():
            return True

        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute

        start_h = self.config.time.START_HOUR
        start_m = self.config.time.START_MINUTE
        finish_h = self.config.time.FINISH_HOUR
        finish_m = self.config.time.FINISH_MINUTE

        # Convert to minutes for easier comparison
        current = hour * 60 + minute
        start = start_h * 60 + start_m
        finish = finish_h * 60 + finish_m

        if start <= finish:
            return start <= current <= finish
        else:
            # Overnight (e.g., 20:00 - 08:00)
            return current >= start or current <= finish

    # ─────────────────────────────────────────────────────────────────────────
    #                           PROFIT TAKING
    # ─────────────────────────────────────────────────────────────────────────

    async def _check_profit_taking(self):
        """Profit taking tekshirish"""
        leverage = self.config.trading.LEVERAGE

        # Single order profit
        should_close, side = self.strategy.check_single_order_profit(
            self.current_price, leverage
        )
        if should_close:
            logger.info(f"Single order profit hit for {side}")
            if side == "buy":
                await self._close_buy_positions()
            else:
                await self._close_sell_positions()
            return

        # Pair global profit
        if self.strategy.check_pair_profit(self.current_price, leverage):
            logger.info("Pair global profit hit")
            await self._close_all_positions()
            return

    # ─────────────────────────────────────────────────────────────────────────
    #                           ORDER MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    async def _check_initial_orders(self):
        """Dastlabki orderlarni tekshirish"""
        # Check if can trade today
        if not self.strategy.can_trade_today():
            return

        # BUY initial order
        if (self.strategy.fire_buy and
            not self.strategy.buy_positions and
            not self.strategy.should_stop_trading()):

            await self._open_buy(self.config.money.BASE_LOT, level=1)
            self.strategy.fire_buy = False
            self.strategy.increment_today_trades()

        # SELL initial order
        if (self.strategy.fire_sell and
            not self.strategy.sell_positions and
            not self.strategy.should_stop_trading()):

            await self._open_sell(self.config.money.BASE_LOT, level=1)
            self.strategy.fire_sell = False
            self.strategy.increment_today_trades()

    async def _check_grid_additions(self):
        """Grid orderlarini tekshirish"""
        # BUY grid
        should_add, level, lot = self.strategy.should_add_buy_grid(self.current_price)
        if should_add:
            await self._open_buy(lot, level)

        # SELL grid
        should_add, level, lot = self.strategy.should_add_sell_grid(self.current_price)
        if should_add:
            await self._open_sell(lot, level)

    async def _open_buy(self, lot: float, level: int):
        """BUY order ochish"""
        try:
            # Lot limitlarni tekshirish
            lot = max(self.config.money.MIN_LOT, min(lot, self.config.money.MAX_LOT))

            result = await self.client.open_long(
                symbol=self.config.trading.SYMBOL,
                size=lot
            )

            order_id = result.get("orderId", str(int(time.time() * 1000)))

            # Add to strategy
            self.strategy.add_position(
                side="buy",
                price=self.current_price,
                lot=lot,
                level=level,
                order_id=order_id
            )

            logger.info(f"Opened BUY: {lot} @ {self.current_price:.2f} (Level {level})")

        except BitgetAPIError as e:
            logger.error(f"Failed to open BUY: {e}")

    async def _open_sell(self, lot: float, level: int):
        """SELL order ochish"""
        try:
            # Lot limitlarni tekshirish
            lot = max(self.config.money.MIN_LOT, min(lot, self.config.money.MAX_LOT))

            result = await self.client.open_short(
                symbol=self.config.trading.SYMBOL,
                size=lot
            )

            order_id = result.get("orderId", str(int(time.time() * 1000)))

            # Add to strategy
            self.strategy.add_position(
                side="sell",
                price=self.current_price,
                lot=lot,
                level=level,
                order_id=order_id
            )

            logger.info(f"Opened SELL: {lot} @ {self.current_price:.2f} (Level {level})")

        except BitgetAPIError as e:
            logger.error(f"Failed to open SELL: {e}")

    async def _close_buy_positions(self):
        """Barcha BUY pozitsiyalarni yopish"""
        if not self.strategy.buy_positions:
            return

        total_lots = self.strategy.get_total_buy_lots()

        try:
            await self.client.close_long(
                symbol=self.config.trading.SYMBOL,
                size=total_lots
            )

            pnl, count = self.strategy.close_buy_positions(
                self.current_price,
                self.config.trading.LEVERAGE
            )

            logger.info(f"Closed {count} BUY positions. PnL: ${pnl:.2f}")

        except BitgetAPIError as e:
            logger.error(f"Failed to close BUY positions: {e}")

    async def _close_sell_positions(self):
        """Barcha SELL pozitsiyalarni yopish"""
        if not self.strategy.sell_positions:
            return

        total_lots = self.strategy.get_total_sell_lots()

        try:
            await self.client.close_short(
                symbol=self.config.trading.SYMBOL,
                size=total_lots
            )

            pnl, count = self.strategy.close_sell_positions(
                self.current_price,
                self.config.trading.LEVERAGE
            )

            logger.info(f"Closed {count} SELL positions. PnL: ${pnl:.2f}")

        except BitgetAPIError as e:
            logger.error(f"Failed to close SELL positions: {e}")

    async def _close_all_positions(self):
        """Barcha pozitsiyalarni yopish"""
        await self._close_buy_positions()
        await self._close_sell_positions()

    # ─────────────────────────────────────────────────────────────────────────
    #                           DISPLAY
    # ─────────────────────────────────────────────────────────────────────────

    def _display_status(self):
        """Status chiqarish"""
        buy_count = len(self.strategy.buy_positions)
        sell_count = len(self.strategy.sell_positions)
        buy_pnl = self.strategy.get_buy_pnl(self.current_price, self.config.trading.LEVERAGE)
        sell_pnl = self.strategy.get_sell_pnl(self.current_price, self.config.trading.LEVERAGE)
        total_pnl = buy_pnl + sell_pnl

        sma = self.strategy.sma.value
        sar = self.strategy.sar.value

        print(f"\r[{self.tick_count}] {self.config.trading.SYMBOL}: ${self.current_price:.2f} | "
              f"SMA: {sma:.2f} SAR: {sar:.2f} | "
              f"BUY: {buy_count} (${buy_pnl:.2f}) | SELL: {sell_count} (${sell_pnl:.2f}) | "
              f"Total: ${total_pnl:.2f} | Balance: ${self.balance:.2f}",
              end="", flush=True)

    # ─────────────────────────────────────────────────────────────────────────
    #                           STATUS METHODS
    # ─────────────────────────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Robot statusini olish"""
        uptime = 0
        if self.start_time:
            uptime = int((datetime.utcnow() - self.start_time).total_seconds())

        return {
            "state": self.state.value,
            "symbol": self.config.trading.SYMBOL,
            "current_price": self.current_price,
            "balance": self.balance,
            "leverage": self.config.trading.LEVERAGE,
            "tick_count": self.tick_count,
            "uptime": uptime,
            "indicators": {
                "sma": self.strategy.sma.value if self.strategy else 0,
                "sar": self.strategy.sar.value if self.strategy else 0,
                "cci": self.strategy.cci.value if self.strategy and self.strategy.cci else 0
            },
            "positions": {
                "buy": [p.to_dict() for p in self.strategy.buy_positions] if self.strategy else [],
                "sell": [p.to_dict() for p in self.strategy.sell_positions] if self.strategy else [],
                "buy_count": len(self.strategy.buy_positions) if self.strategy else 0,
                "sell_count": len(self.strategy.sell_positions) if self.strategy else 0,
                "buy_pnl": self.strategy.get_buy_pnl(self.current_price, self.config.trading.LEVERAGE) if self.strategy else 0,
                "sell_pnl": self.strategy.get_sell_pnl(self.current_price, self.config.trading.LEVERAGE) if self.strategy else 0
            },
            "stats": self.strategy.get_stats() if self.strategy else {},
            "config": {
                "multiplier": self.config.grid.MULTIPLIER,
                "space_percent": self.config.grid.SPACE_PERCENT,
                "single_order_profit": self.config.profit.SINGLE_ORDER_PROFIT,
                "pair_global_profit": self.config.profit.PAIR_GLOBAL_PROFIT
            }
        }
