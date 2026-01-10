"""
Hedging Grid Robot - Trading Strategiyasi

Grid hedging strategiyasi: Buy va Sell tomonlari mustaqil boshqariladi
"""

import logging
import time
import uuid
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from datetime import datetime

from .config import RobotConfig, GridConfig, EntryConfig, ProfitConfig
from .indicators import Candle, SMAIndicator, ParabolicSARIndicator, CCIIndicator

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               POSITION DATA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HedgingPosition:
    """Grid pozitsiya ma'lumotlari"""
    id: str
    side: str  # 'buy' or 'sell'
    entry_price: float
    lot: float
    grid_level: int  # 1, 2, 3, or 4
    pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)
    opened_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "side": self.side,
            "entry_price": self.entry_price,
            "lot": self.lot,
            "grid_level": self.grid_level,
            "pnl": self.pnl,
            "timestamp": self.timestamp,
            "opened_at": self.opened_at
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                           HEDGING STRATEGY
# ═══════════════════════════════════════════════════════════════════════════════

class HedgingStrategy:
    """
    Grid Hedging Trading Strategy

    MQL4 EA dan portlangan:
    - SMA/Parabolic SAR yoki CCI entry signallari
    - 4 darajali grid system
    - Martingale lot scaling
    - Buy va Sell tomonlari mustaqil
    """

    def __init__(self, config: RobotConfig):
        """
        Args:
            config: Robot konfiguratsiyasi
        """
        self.config = config
        self.grid = config.grid
        self.entry = config.entry
        self.profit = config.profit

        # Indicators
        self.sma = SMAIndicator(period=config.entry.SMA_PERIOD, ma_type='lwma')
        self.sar = ParabolicSARIndicator(
            af_start=config.entry.SAR_AF,
            af_max=config.entry.SAR_MAX
        )
        self.cci = CCIIndicator(period=config.entry.CCI_PERIOD) if config.entry.CCI_PERIOD > 0 else None

        # Positions (separate buy/sell)
        self.buy_positions: List[HedgingPosition] = []
        self.sell_positions: List[HedgingPosition] = []

        # Entry flags
        self.fire_buy: bool = False
        self.fire_sell: bool = False

        # CCI allowed flags (reset when in neutral zone)
        self.buy_allowed: bool = True
        self.sell_allowed: bool = True

        # Stats
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit": 0.0,
            "win_rate": 0.0
        }

        # Trading state
        self._stop_trading: bool = False
        self._today_trades: int = 0
        self._today_date: str = ""

    # ─────────────────────────────────────────────────────────────────────────
    #                           INDICATOR METHODS
    # ─────────────────────────────────────────────────────────────────────────

    def update_indicators(self, candles: List[Candle]):
        """
        Indikatorlarni yangilash

        Args:
            candles: Candle ma'lumotlari
        """
        if len(candles) < 10:
            logger.warning("Not enough candles for indicators")
            return

        # SMA va SAR
        self.sma.calculate(candles)
        self.sar.calculate(candles)

        # CCI (agar yoqilgan bo'lsa)
        if self.cci:
            self.cci.calculate(candles)

    def check_entry_signals(self, is_new_bar: bool):
        """
        Entry signallarini tekshirish

        Args:
            is_new_bar: Yangi sham ochildimi?
        """
        if not is_new_bar:
            return

        # SMA/Parabolic SAR entry
        if self.entry.USE_SMA_SAR:
            self._check_sma_sar_signals()

        # CCI entry
        if self.cci and self.entry.CCI_PERIOD > 0:
            self._check_cci_signals()

    def _check_sma_sar_signals(self):
        """SMA/Parabolic SAR signallarini tekshirish"""
        sma = self.sma.value
        sar = self.sar.value

        if sma == 0 or sar == 0:
            return

        if self.entry.REVERSE_ORDER:
            # Reversed logic
            if sar < sma:
                self.fire_sell = False
                self.fire_buy = True
            elif sar > sma:
                self.fire_sell = True
                self.fire_buy = False
        else:
            # Normal logic
            if sar < sma:
                self.fire_sell = True
                self.fire_buy = False
            elif sar > sma:
                self.fire_sell = False
                self.fire_buy = True

        logger.debug(f"SMA/SAR signal: SMA={sma:.2f}, SAR={sar:.2f}, "
                     f"fire_buy={self.fire_buy}, fire_sell={self.fire_sell}")

    def _check_cci_signals(self):
        """CCI signallarini tekshirish"""
        cci = self.cci.value

        # Sell signal: CCI < ccimin
        if cci < self.entry.CCI_MIN and self.sell_allowed:
            self.fire_sell = True
            self.sell_allowed = False

        # Buy signal: CCI > ccimax
        if cci > self.entry.CCI_MAX and self.buy_allowed:
            self.fire_buy = True
            self.buy_allowed = False

        # Reset when in neutral zone
        if self.entry.CCI_MIN < cci < self.entry.CCI_MAX:
            self.buy_allowed = True
            self.sell_allowed = True

        logger.debug(f"CCI signal: CCI={cci:.2f}, fire_buy={self.fire_buy}, fire_sell={self.fire_sell}")

    # ─────────────────────────────────────────────────────────────────────────
    #                           GRID LOGIC
    # ─────────────────────────────────────────────────────────────────────────

    def get_grid_level(self, order_count: int) -> int:
        """
        Order count asosida grid levelni aniqlash

        Args:
            order_count: Joriy orderlar soni

        Returns:
            Grid level (1-4)
        """
        level1_max = self.grid.SPACE_ORDERS
        level2_max = level1_max + self.grid.SPACE1_ORDERS
        level3_max = level2_max + self.grid.SPACE2_ORDERS

        if order_count < level1_max:
            return 1
        elif order_count < level2_max:
            return 2
        elif order_count < level3_max:
            return 3
        else:
            return 4

    def get_grid_distance(self, level: int) -> float:
        """
        Grid level uchun distance (foizda) olish

        Args:
            level: Grid level (1-4)

        Returns:
            Distance (percent)
        """
        distances = {
            1: self.grid.SPACE_PERCENT,
            2: self.grid.SPACE1_PERCENT,
            3: self.grid.SPACE2_PERCENT,
            4: self.grid.SPACE3_PERCENT
        }
        return distances.get(level, self.grid.SPACE_PERCENT)

    def get_grid_lot(self, level: int, last_lot: float) -> float:
        """
        Grid level uchun lot hajmini hisoblash

        Args:
            level: Grid level (1-4)
            last_lot: Oxirgi order lot hajmi

        Returns:
            Yangi lot hajmi
        """
        if self.grid.MULTIPLIER > 0:
            # Martingale
            return round(last_lot * self.grid.MULTIPLIER, 4)
        else:
            # Fixed lots
            lots = {
                1: self.grid.SPACE_LOTS,
                2: self.grid.SPACE1_LOTS,
                3: self.grid.SPACE2_LOTS,
                4: self.grid.SPACE3_LOTS
            }
            return lots.get(level, self.grid.SPACE_LOTS)

    def should_add_buy_grid(self, current_price: float) -> Tuple[bool, int, float]:
        """
        Buy grid order qo'shish kerakmi?

        Args:
            current_price: Joriy narx (Ask)

        Returns:
            (should_add, grid_level, lot_size)
        """
        if not self.buy_positions:
            return False, 0, 0.0

        # Eng katta (eng past narxdagi) buy pozitsiyani topish
        largest = self.get_largest_buy_position()
        if not largest:
            return False, 0, 0.0

        order_count = len(self.buy_positions)
        max_orders = self.grid.get_max_orders()

        if order_count >= max_orders:
            return False, 0, 0.0

        # Grid level aniqlash
        level = self.get_grid_level(order_count)
        distance = self.get_grid_distance(level)

        # Buy uchun: narx pastga tushishi kerak
        trigger_price = largest.entry_price * (1 - distance / 100)

        if current_price <= trigger_price:
            lot = self.get_grid_lot(level, largest.lot)
            return True, level, lot

        return False, 0, 0.0

    def should_add_sell_grid(self, current_price: float) -> Tuple[bool, int, float]:
        """
        Sell grid order qo'shish kerakmi?

        Args:
            current_price: Joriy narx (Bid)

        Returns:
            (should_add, grid_level, lot_size)
        """
        if not self.sell_positions:
            return False, 0, 0.0

        # Eng katta (eng yuqori narxdagi) sell pozitsiyani topish
        largest = self.get_largest_sell_position()
        if not largest:
            return False, 0, 0.0

        order_count = len(self.sell_positions)
        max_orders = self.grid.get_max_orders()

        if order_count >= max_orders:
            return False, 0, 0.0

        # Grid level aniqlash
        level = self.get_grid_level(order_count)
        distance = self.get_grid_distance(level)

        # Sell uchun: narx yuqoriga ko'tarilishi kerak
        trigger_price = largest.entry_price * (1 + distance / 100)

        if current_price >= trigger_price:
            lot = self.get_grid_lot(level, largest.lot)
            return True, level, lot

        return False, 0, 0.0

    # ─────────────────────────────────────────────────────────────────────────
    #                           POSITION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def add_position(self, side: str, price: float, lot: float,
                     level: int, order_id: str) -> HedgingPosition:
        """
        Yangi pozitsiya qo'shish

        Args:
            side: 'buy' yoki 'sell'
            price: Entry narx
            lot: Lot hajmi
            level: Grid level
            order_id: Exchange order ID

        Returns:
            Yaratilgan pozitsiya
        """
        position = HedgingPosition(
            id=order_id,
            side=side,
            entry_price=price,
            lot=lot,
            grid_level=level
        )

        if side == 'buy':
            self.buy_positions.append(position)
        else:
            self.sell_positions.append(position)

        self.stats["total_trades"] += 1
        logger.info(f"Position added: {side.upper()} {lot} @ {price:.2f} (Level {level})")

        return position

    def get_largest_buy_position(self) -> Optional[HedgingPosition]:
        """Eng katta (eng past narxdagi) buy pozitsiyani olish"""
        if not self.buy_positions:
            return None
        return min(self.buy_positions, key=lambda p: p.entry_price)

    def get_largest_sell_position(self) -> Optional[HedgingPosition]:
        """Eng katta (eng yuqori narxdagi) sell pozitsiyani olish"""
        if not self.sell_positions:
            return None
        return max(self.sell_positions, key=lambda p: p.entry_price)

    def get_buy_pnl(self, current_price: float, leverage: int = 1) -> float:
        """
        Buy pozitsiyalarning PnL ni hisoblash

        Args:
            current_price: Joriy narx
            leverage: Leverage

        Returns:
            Total PnL (USDT)
        """
        total_pnl = 0.0
        for pos in self.buy_positions:
            # Buy: (current - entry) * lot * leverage
            pnl = (current_price - pos.entry_price) * pos.lot * leverage
            pos.pnl = pnl
            total_pnl += pnl
        return total_pnl

    def get_sell_pnl(self, current_price: float, leverage: int = 1) -> float:
        """
        Sell pozitsiyalarning PnL ni hisoblash

        Args:
            current_price: Joriy narx
            leverage: Leverage

        Returns:
            Total PnL (USDT)
        """
        total_pnl = 0.0
        for pos in self.sell_positions:
            # Sell: (entry - current) * lot * leverage
            pnl = (pos.entry_price - current_price) * pos.lot * leverage
            pos.pnl = pnl
            total_pnl += pnl
        return total_pnl

    def get_total_pnl(self, current_price: float, leverage: int = 1) -> float:
        """Jami PnL"""
        return self.get_buy_pnl(current_price, leverage) + self.get_sell_pnl(current_price, leverage)

    def get_average_buy_price(self) -> float:
        """Buy pozitsiyalarining o'rtacha narxi"""
        if not self.buy_positions:
            return 0.0
        total_value = sum(p.entry_price * p.lot for p in self.buy_positions)
        total_lot = sum(p.lot for p in self.buy_positions)
        return total_value / total_lot if total_lot > 0 else 0.0

    def get_average_sell_price(self) -> float:
        """Sell pozitsiyalarining o'rtacha narxi"""
        if not self.sell_positions:
            return 0.0
        total_value = sum(p.entry_price * p.lot for p in self.sell_positions)
        total_lot = sum(p.lot for p in self.sell_positions)
        return total_value / total_lot if total_lot > 0 else 0.0

    def get_total_buy_lots(self) -> float:
        """Buy pozitsiyalarining jami loti"""
        return sum(p.lot for p in self.buy_positions)

    def get_total_sell_lots(self) -> float:
        """Sell pozitsiyalarining jami loti"""
        return sum(p.lot for p in self.sell_positions)

    # ─────────────────────────────────────────────────────────────────────────
    #                           PROFIT TAKING
    # ─────────────────────────────────────────────────────────────────────────

    def check_single_order_profit(self, current_price: float, leverage: int = 1) -> Tuple[bool, str]:
        """
        Bitta order profitini tekshirish

        Returns:
            (should_close, side)
        """
        total_orders = len(self.buy_positions) + len(self.sell_positions)

        if total_orders != 1:
            return False, ""

        if len(self.buy_positions) == 1:
            pnl = self.get_buy_pnl(current_price, leverage)
            if pnl >= self.profit.SINGLE_ORDER_PROFIT:
                return True, "buy"

        if len(self.sell_positions) == 1:
            pnl = self.get_sell_pnl(current_price, leverage)
            if pnl >= self.profit.SINGLE_ORDER_PROFIT:
                return True, "sell"

        return False, ""

    def check_pair_profit(self, current_price: float, leverage: int = 1) -> bool:
        """
        Buy+Sell juftligi profitini tekshirish

        Returns:
            should_close_all
        """
        if self.profit.PAIR_GLOBAL_PROFIT <= 0:
            return False

        total_orders = len(self.buy_positions) + len(self.sell_positions)
        if total_orders <= 1:
            return False

        total_pnl = self.get_total_pnl(current_price, leverage)
        return total_pnl >= self.profit.PAIR_GLOBAL_PROFIT

    def check_side_profit(self, side: str, current_price: float,
                          profit_target: float, leverage: int = 1) -> bool:
        """
        Bir tomonning profitini tekshirish

        Args:
            side: 'buy' yoki 'sell'
            current_price: Joriy narx
            profit_target: Profit target (USDT)
            leverage: Leverage

        Returns:
            should_close
        """
        if profit_target <= 0:
            return False

        if side == "buy":
            pnl = self.get_buy_pnl(current_price, leverage)
        else:
            pnl = self.get_sell_pnl(current_price, leverage)

        return pnl >= profit_target

    def check_global_limits(self, current_price: float, leverage: int = 1) -> Tuple[bool, str]:
        """
        Global profit/loss limitlarini tekshirish

        Returns:
            (should_stop, reason)
        """
        total_pnl = self.get_total_pnl(current_price, leverage)

        # Global profit limit
        if self.profit.GLOBAL_PROFIT > 0 and total_pnl >= self.profit.GLOBAL_PROFIT:
            return True, "GLOBAL_PROFIT"

        # Max loss limit
        if self.profit.MAX_LOSS < 0 and total_pnl <= self.profit.MAX_LOSS:
            return True, "MAX_LOSS"

        return False, ""

    # ─────────────────────────────────────────────────────────────────────────
    #                           CLOSE POSITIONS
    # ─────────────────────────────────────────────────────────────────────────

    def close_buy_positions(self, close_price: float, leverage: int = 1) -> Tuple[float, int]:
        """
        Barcha buy pozitsiyalarni yopish

        Returns:
            (total_pnl, positions_closed)
        """
        total_pnl = self.get_buy_pnl(close_price, leverage)
        count = len(self.buy_positions)

        # Update stats
        if total_pnl > 0:
            self.stats["winning_trades"] += count
        else:
            self.stats["losing_trades"] += count
        self.stats["total_profit"] += total_pnl
        self._update_win_rate()

        # Clear positions
        self.buy_positions.clear()
        self.fire_buy = False

        logger.info(f"Closed {count} BUY positions with PnL: ${total_pnl:.2f}")
        return total_pnl, count

    def close_sell_positions(self, close_price: float, leverage: int = 1) -> Tuple[float, int]:
        """
        Barcha sell pozitsiyalarni yopish

        Returns:
            (total_pnl, positions_closed)
        """
        total_pnl = self.get_sell_pnl(close_price, leverage)
        count = len(self.sell_positions)

        # Update stats
        if total_pnl > 0:
            self.stats["winning_trades"] += count
        else:
            self.stats["losing_trades"] += count
        self.stats["total_profit"] += total_pnl
        self._update_win_rate()

        # Clear positions
        self.sell_positions.clear()
        self.fire_sell = False

        logger.info(f"Closed {count} SELL positions with PnL: ${total_pnl:.2f}")
        return total_pnl, count

    def close_all_positions(self, close_price: float, leverage: int = 1) -> Tuple[float, int]:
        """
        Barcha pozitsiyalarni yopish

        Returns:
            (total_pnl, positions_closed)
        """
        buy_pnl, buy_count = self.close_buy_positions(close_price, leverage)
        sell_pnl, sell_count = self.close_sell_positions(close_price, leverage)
        return buy_pnl + sell_pnl, buy_count + sell_count

    def _update_win_rate(self):
        """Win rate ni yangilash"""
        total = self.stats["winning_trades"] + self.stats["losing_trades"]
        if total > 0:
            self.stats["win_rate"] = round(self.stats["winning_trades"] / total * 100, 2)

    # ─────────────────────────────────────────────────────────────────────────
    #                           UTILITY METHODS
    # ─────────────────────────────────────────────────────────────────────────

    def can_trade_today(self) -> bool:
        """Bugun savdo qilish mumkinmi?"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_trades = 0

        return self._today_trades < self.profit.TRADES_PER_DAY

    def increment_today_trades(self):
        """Bugungi savdolarni oshirish"""
        self._today_trades += 1

    def should_stop_trading(self) -> bool:
        """Savdoni to'xtatish kerakmi?"""
        return self._stop_trading

    def stop_trading(self):
        """Savdoni to'xtatish"""
        self._stop_trading = True

    def reset(self):
        """Strategiyani reset qilish"""
        self.buy_positions.clear()
        self.sell_positions.clear()
        self.fire_buy = False
        self.fire_sell = False
        self.buy_allowed = True
        self.sell_allowed = True
        self._stop_trading = False
        self.sar.reset()

    def get_stats(self) -> Dict:
        """Statistikani olish"""
        return {
            **self.stats,
            "buy_positions": len(self.buy_positions),
            "sell_positions": len(self.sell_positions),
            "today_trades": self._today_trades
        }
