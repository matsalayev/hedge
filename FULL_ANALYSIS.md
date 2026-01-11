# Hedging Grid Robot - To'liq Texnik Analiz

## Loyiha Haqida

**Nom:** Hedging Grid Robot
**Versiya:** 1.0.0
**Til:** Python 3.11+
**Port:** 8082
**Strategiya:** Grid Hedging + SMA/SAR/CCI Indicators
**Birja:** Bitget Futures

---

## 1. ARXITEKTURA

### 1.1 Fayl Tuzilishi

```
hedging_robot/
├── run.py                 # CLI entry point (standalone)
├── run_server.py          # Server entry point (HEMA integration)
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container build
├── docker-compose.yml     # Container orchestration
├── CLAUDE.md              # Project documentation
└── hedging_robot/
    ├── __init__.py
    ├── config.py          # Configuration management (~350 qator)
    ├── indicators.py      # SMA/SAR/CCI indicators (~300 qator)
    ├── strategy.py        # Grid trading logic (~700 qator)
    ├── robot.py           # Main trading loop (~550 qator)
    ├── api_client.py      # Bitget REST API (~550 qator)
    ├── webhook_client.py  # HEMA webhooks (~600 qator)
    ├── session_manager.py # Multi-user sessions (~900 qator)
    └── server.py          # FastAPI server (~950 qator)
```

### 1.2 Komponentlar Diagrammasi

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Hedging Grid Robot                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   server.py  │───▶│ session_     │───▶│   robot.py   │          │
│  │   (FastAPI)  │    │ manager.py   │    │  (Async Loop)│          │
│  └──────────────┘    └──────────────┘    └──────┬───────┘          │
│         │                                        │                   │
│         │                                        ▼                   │
│         │                              ┌──────────────┐              │
│         │                              │  strategy.py │              │
│         │                              │ (Grid Logic) │              │
│         │                              └──────┬───────┘              │
│         │                                     │                      │
│         ▼                                     ▼                      │
│  ┌──────────────┐                    ┌──────────────┐               │
│  │   webhook_   │◀───────────────────│ indicators.py│               │
│  │  client.py   │                    │ (SMA/SAR/CCI)│               │
│  └──────┬───────┘                    └──────────────┘               │
│         │                                     │                      │
│         │                                     ▼                      │
│         │                            ┌──────────────┐               │
│         │                            │ api_client.py│               │
│         │                            │  (Bitget)    │               │
│         │                            └──────┬───────┘               │
│         │                                   │                       │
└─────────┼───────────────────────────────────┼───────────────────────┘
          │                                   │
          ▼                                   ▼
   ┌──────────────┐                  ┌──────────────┐
   │    HEMA      │                  │   Bitget     │
   │  Platform    │                  │  Exchange    │
   └──────────────┘                  └──────────────┘
```

### 1.3 Grid Tuzilishi

```
                           SELL Side
    ┌─────────────────────────────────────────────────────┐
    │  Level 4: SPACE3_PERCENT (3%)                       │
    │  Level 3: SPACE2_PERCENT (2%)                       │
    │  Level 2: SPACE1_PERCENT (1%)                       │
    │  Level 1: SPACE_PERCENT (0.5%)                      │
    ├─────────────────────────────────────────────────────┤
    │                  CURRENT PRICE                       │
    ├─────────────────────────────────────────────────────┤
    │  Level 1: SPACE_PERCENT (0.5%)                      │
    │  Level 2: SPACE1_PERCENT (1%)                       │
    │  Level 3: SPACE2_PERCENT (2%)                       │
    │  Level 4: SPACE3_PERCENT (3%)                       │
    └─────────────────────────────────────────────────────┘
                            BUY Side
```

---

## 2. KONFIGURATSIYA

### 2.1 Environment Variables

```bash
# ═══════════════════════════════════════════════════════════════
# API CREDENTIALS
# ═══════════════════════════════════════════════════════════════
BITGET_API_KEY=your_api_key
BITGET_SECRET_KEY=your_secret_key
BITGET_PASSPHRASE=your_passphrase
DEMO_MODE=true

# ═══════════════════════════════════════════════════════════════
# TRADING PARAMETERS
# ═══════════════════════════════════════════════════════════════
TRADING_SYMBOL=BTCUSDT
LEVERAGE=10
TICK_INTERVAL=1.0
TIMEFRAME=1H
OPEN_ON_NEW_CANDLE=true

# ═══════════════════════════════════════════════════════════════
# GRID LEVEL 1
# ═══════════════════════════════════════════════════════════════
SPACE_PERCENT=0.5           # Distance from entry
SPACE_ORDERS=5              # Max orders at this level
SPACE_LOTS=0.001            # Lot size (if MULTIPLIER=0)

# ═══════════════════════════════════════════════════════════════
# GRID LEVEL 2
# ═══════════════════════════════════════════════════════════════
SPACE1_PERCENT=1.0
SPACE1_ORDERS=5
SPACE1_LOTS=0.002

# ═══════════════════════════════════════════════════════════════
# GRID LEVEL 3
# ═══════════════════════════════════════════════════════════════
SPACE2_PERCENT=2.0
SPACE2_ORDERS=5
SPACE2_LOTS=0.003

# ═══════════════════════════════════════════════════════════════
# GRID LEVEL 4
# ═══════════════════════════════════════════════════════════════
SPACE3_PERCENT=3.0
SPACE3_ORDERS=5
SPACE3_LOTS=0.004

# ═══════════════════════════════════════════════════════════════
# LOT SIZING
# ═══════════════════════════════════════════════════════════════
MULTIPLIER=1.5              # Martingale multiplier (0 = fixed lots)
BASE_LOT=0.001
MIN_LOT=0.001
MAX_LOT=50.0

# ═══════════════════════════════════════════════════════════════
# ENTRY SIGNALS - SMA/SAR
# ═══════════════════════════════════════════════════════════════
USE_SMA_SAR=true
SMA_PERIOD=7
SAR_AF=0.1                  # Acceleration Factor
SAR_MAX=0.8                 # Max AF
REVERSE_ORDER=false         # true = reverse signals

# ═══════════════════════════════════════════════════════════════
# ENTRY SIGNALS - CCI
# ═══════════════════════════════════════════════════════════════
CCI_PERIOD=0                # 0 = disabled
CCI_MAX=100                 # Sell when CCI crosses above
CCI_MIN=-100                # Buy when CCI crosses below

# ═══════════════════════════════════════════════════════════════
# PROFIT TARGETS
# ═══════════════════════════════════════════════════════════════
SINGLE_ORDER_PROFIT=3.0     # Close single position at this %
PAIR_GLOBAL_PROFIT=1.0      # Close all when combined profit %
GLOBAL_PROFIT=0             # Daily profit target (0 = disabled)
MAX_LOSS=0                  # Daily max loss (0 = disabled)

# ═══════════════════════════════════════════════════════════════
# TIME FILTER
# ═══════════════════════════════════════════════════════════════
START_HOUR=0
START_MINUTE=0
FINISH_HOUR=23
FINISH_MINUTE=59

# ═══════════════════════════════════════════════════════════════
# SERVER SETTINGS
# ═══════════════════════════════════════════════════════════════
SERVER_PORT=8082
BOT_ID=hedging-grid-bot
BOT_NAME=Hedging Grid Robot
BOT_VERSION=1.0.0
BOT_SECRET=your_webhook_secret
```

### 2.2 Grid Level Configuration

```python
# config.py

@dataclass
class GridLevel:
    """Single grid level configuration."""
    percent: float      # Distance from last entry
    max_orders: int     # Maximum orders at this level
    lot_size: float     # Fixed lot (if multiplier=0)

@dataclass
class GridConfig:
    """Full grid configuration."""
    levels: List[GridLevel]
    multiplier: float   # Martingale multiplier
    base_lot: float
    min_lot: float
    max_lot: float

    @classmethod
    def from_env(cls) -> 'GridConfig':
        return cls(
            levels=[
                GridLevel(
                    percent=float(os.getenv('SPACE_PERCENT', 0.5)),
                    max_orders=int(os.getenv('SPACE_ORDERS', 5)),
                    lot_size=float(os.getenv('SPACE_LOTS', 0.001))
                ),
                GridLevel(
                    percent=float(os.getenv('SPACE1_PERCENT', 1.0)),
                    max_orders=int(os.getenv('SPACE1_ORDERS', 5)),
                    lot_size=float(os.getenv('SPACE1_LOTS', 0.002))
                ),
                GridLevel(
                    percent=float(os.getenv('SPACE2_PERCENT', 2.0)),
                    max_orders=int(os.getenv('SPACE2_ORDERS', 5)),
                    lot_size=float(os.getenv('SPACE2_LOTS', 0.003))
                ),
                GridLevel(
                    percent=float(os.getenv('SPACE3_PERCENT', 3.0)),
                    max_orders=int(os.getenv('SPACE3_ORDERS', 5)),
                    lot_size=float(os.getenv('SPACE3_LOTS', 0.004))
                ),
            ],
            multiplier=float(os.getenv('MULTIPLIER', 1.5)),
            base_lot=float(os.getenv('BASE_LOT', 0.001)),
            min_lot=float(os.getenv('MIN_LOT', 0.001)),
            max_lot=float(os.getenv('MAX_LOT', 50.0))
        )
```

---

## 3. INDIKATORLAR

### 3.1 SMA (Linear Weighted Moving Average)

```python
# indicators.py

class SMAIndicator:
    """
    Linear Weighted Moving Average using weighted price.
    Weighted Price = (High + Low + Close + Close) / 4

    LWMA = Σ(Price[i] × Weight[i]) / Σ(Weight[i])
    Weight = 1, 2, 3, ..., N (oldest to newest)
    """

    def __init__(self, period: int = 7):
        self.period = period

    def calculate(self, candles: List[dict]) -> float:
        if len(candles) < self.period:
            return 0.0

        # Calculate weighted prices
        weighted_prices = []
        for candle in candles[-self.period:]:
            wp = (candle['high'] + candle['low'] + candle['close'] * 2) / 4
            weighted_prices.append(wp)

        # Apply linear weights
        weights = list(range(1, self.period + 1))
        weighted_sum = sum(p * w for p, w in zip(weighted_prices, weights))
        weight_total = sum(weights)

        return weighted_sum / weight_total
```

### 3.2 Parabolic SAR

```python
# indicators.py

class ParabolicSAR:
    """
    Parabolic Stop and Reverse indicator.

    Parameters:
    - af_start: Initial Acceleration Factor (default 0.1)
    - af_max: Maximum AF (default 0.8)

    Logic:
    - Uptrend: SAR below price, EP = highest high
    - Downtrend: SAR above price, EP = lowest low
    - Reversal when price crosses SAR
    """

    def __init__(self, af_start: float = 0.1, af_max: float = 0.8):
        self.af_start = af_start
        self.af_max = af_max
        self.af = af_start
        self.ep = None          # Extreme Point
        self.sar = None
        self.trend = None       # 1 = up, -1 = down

    def calculate(self, candles: List[dict]) -> float:
        if len(candles) < 2:
            return 0.0

        current = candles[-1]
        previous = candles[-2]

        # Initialize on first calculation
        if self.sar is None:
            self._initialize(candles)
            return self.sar

        # Calculate new SAR
        new_sar = self.sar + self.af * (self.ep - self.sar)

        # Apply constraints
        if self.trend == 1:  # Uptrend
            new_sar = min(new_sar, previous['low'], candles[-3]['low'] if len(candles) > 2 else previous['low'])

            # Check for reversal
            if current['low'] < new_sar:
                self._reverse_to_downtrend(current)
            else:
                # Update EP and AF
                if current['high'] > self.ep:
                    self.ep = current['high']
                    self.af = min(self.af + self.af_start, self.af_max)
                self.sar = new_sar

        else:  # Downtrend
            new_sar = max(new_sar, previous['high'], candles[-3]['high'] if len(candles) > 2 else previous['high'])

            # Check for reversal
            if current['high'] > new_sar:
                self._reverse_to_uptrend(current)
            else:
                # Update EP and AF
                if current['low'] < self.ep:
                    self.ep = current['low']
                    self.af = min(self.af + self.af_start, self.af_max)
                self.sar = new_sar

        return self.sar

    def _initialize(self, candles: List[dict]):
        """Initialize SAR based on recent price action."""
        recent = candles[-5:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]

        # Determine initial trend
        if candles[-1]['close'] > candles[-2]['close']:
            self.trend = 1
            self.ep = max(highs)
            self.sar = min(lows)
        else:
            self.trend = -1
            self.ep = min(lows)
            self.sar = max(highs)

        self.af = self.af_start

    def _reverse_to_uptrend(self, current: dict):
        self.trend = 1
        self.sar = self.ep
        self.ep = current['high']
        self.af = self.af_start

    def _reverse_to_downtrend(self, current: dict):
        self.trend = -1
        self.sar = self.ep
        self.ep = current['low']
        self.af = self.af_start
```

### 3.3 CCI (Commodity Channel Index)

```python
# indicators.py

class CCIIndicator:
    """
    Commodity Channel Index.

    CCI = (Typical Price - SMA(TP)) / (0.015 × Mean Deviation)
    Typical Price = (High + Low + Close) / 3

    Signals:
    - CCI > +100: Overbought (potential SELL)
    - CCI < -100: Oversold (potential BUY)
    """

    def __init__(self, period: int = 20):
        self.period = period
        self.history: List[float] = []

    def calculate(self, candles: List[dict]) -> float:
        if len(candles) < self.period:
            return 0.0

        # Calculate typical prices
        typical_prices = []
        for candle in candles[-self.period:]:
            tp = (candle['high'] + candle['low'] + candle['close']) / 3
            typical_prices.append(tp)

        # SMA of typical prices
        sma = sum(typical_prices) / self.period

        # Mean deviation
        mean_dev = sum(abs(tp - sma) for tp in typical_prices) / self.period

        # CCI calculation
        current_tp = typical_prices[-1]
        if mean_dev == 0:
            cci = 0.0
        else:
            cci = (current_tp - sma) / (0.015 * mean_dev)

        # Store history for cross detection
        self.history.append(cci)
        if len(self.history) > 100:
            self.history.pop(0)

        return cci

    def crossed_above(self, level: float) -> bool:
        """Check if CCI crossed above level."""
        if len(self.history) < 2:
            return False
        return self.history[-2] < level and self.history[-1] >= level

    def crossed_below(self, level: float) -> bool:
        """Check if CCI crossed below level."""
        if len(self.history) < 2:
            return False
        return self.history[-2] > level and self.history[-1] <= level
```

---

## 4. TRADING LOGIC

### 4.1 Entry Signal Detection

```python
# strategy.py

class HedgingStrategy:
    def detect_entry_signal(self, sma: float, sar: float, cci: float) -> str:
        """
        Determine entry signal based on indicators.

        SMA/SAR Logic:
        - Normal:   BUY if SAR > SMA (price above support)
        - Normal:   SELL if SAR < SMA (price below resistance)
        - Reversed: Opposite logic

        CCI Logic:
        - BUY when CCI crosses above CCI_MAX (+100)
        - SELL when CCI crosses below CCI_MIN (-100)

        Returns: "BUY", "SELL", or "NONE"
        """
        signal = "NONE"

        # SMA/SAR signal
        if self.config.use_sma_sar:
            if self.config.reverse_order:
                # Reversed logic
                if sar < sma:
                    signal = "BUY"
                elif sar > sma:
                    signal = "SELL"
            else:
                # Normal logic
                if sar > sma:
                    signal = "BUY"
                elif sar < sma:
                    signal = "SELL"

        # CCI signal (overrides SMA/SAR if enabled)
        if self.config.cci_period > 0:
            if self.cci.crossed_above(self.config.cci_max):
                signal = "SELL"  # Overbought
            elif self.cci.crossed_below(self.config.cci_min):
                signal = "BUY"   # Oversold

        return signal
```

### 4.2 Grid Level Calculation

```python
# strategy.py

def get_current_grid_level(self, positions: List[Position]) -> int:
    """
    Determine current grid level based on position count.

    Level 0: 0 positions
    Level 1: 1-5 positions (SPACE_ORDERS)
    Level 2: 6-10 positions (SPACE1_ORDERS)
    Level 3: 11-15 positions (SPACE2_ORDERS)
    Level 4: 16-20 positions (SPACE3_ORDERS)
    """
    count = len(positions)
    cumulative = 0

    for i, level in enumerate(self.config.grid.levels):
        cumulative += level.max_orders
        if count < cumulative:
            return i

    return len(self.config.grid.levels) - 1

def get_grid_distance(self, level: int) -> float:
    """Get distance percentage for grid level."""
    if level < len(self.config.grid.levels):
        return self.config.grid.levels[level].percent
    return self.config.grid.levels[-1].percent
```

### 4.3 Grid Addition Logic

```python
# strategy.py

def can_add_grid_order(self, side: str, current_price: float) -> Tuple[bool, float]:
    """
    Check if we can add a new grid order.

    BUY: Add when price drops below lowest_entry × (1 - grid_distance%)
    SELL: Add when price rises above highest_entry × (1 + grid_distance%)

    Returns: (can_add: bool, lot_size: float)
    """
    positions = self.buy_positions if side == "BUY" else self.sell_positions

    if not positions:
        return True, self._calculate_lot(0)

    # Check max orders
    total_positions = len(self.buy_positions) + len(self.sell_positions)
    max_total = sum(l.max_orders for l in self.config.grid.levels) * 2
    if total_positions >= max_total:
        return False, 0.0

    # Get current grid level
    level = self.get_current_grid_level(positions)
    distance = self.get_grid_distance(level)

    # Calculate trigger price
    if side == "BUY":
        lowest_entry = min(p.entry_price for p in positions)
        trigger_price = lowest_entry * (1 - distance / 100)

        if current_price <= trigger_price:
            lot = self._calculate_lot(len(positions))
            return True, lot
    else:
        highest_entry = max(p.entry_price for p in positions)
        trigger_price = highest_entry * (1 + distance / 100)

        if current_price >= trigger_price:
            lot = self._calculate_lot(len(positions))
            return True, lot

    return False, 0.0
```

### 4.4 Lot Sizing (Martingale)

```python
# strategy.py

def _calculate_lot(self, position_count: int) -> float:
    """
    Calculate lot size for next position.

    If MULTIPLIER > 0: Martingale
        Lot = last_lot × MULTIPLIER

    If MULTIPLIER = 0: Fixed lots per level
        Use SPACE_LOTS, SPACE1_LOTS, etc.
    """
    if self.config.grid.multiplier > 0:
        # Martingale
        if position_count == 0:
            lot = self.config.grid.base_lot
        else:
            last_lot = self._get_last_lot()
            lot = last_lot * self.config.grid.multiplier
    else:
        # Fixed lots per level
        level = self.get_current_grid_level_by_count(position_count)
        lot = self.config.grid.levels[level].lot_size

    # Clamp to min/max
    lot = max(self.config.grid.min_lot, min(self.config.grid.max_lot, lot))
    return lot
```

### 4.5 Profit Taking Logic

```python
# strategy.py

async def check_profit_targets(self, current_price: float) -> List[str]:
    """
    Check all profit targets in priority order.

    Priority:
    1. Single Order Profit - Close individual profitable positions
    2. Pair Global Profit - Close all if combined profit target met
    3. Global Profit - Stop trading if daily profit target reached
    4. Max Loss - Stop trading if daily loss limit reached

    Returns: List of actions taken
    """
    actions = []

    # 1. Single Order Profit
    if self.config.profit.single_order_profit > 0:
        for pos in self.buy_positions[:]:
            pnl_percent = self._calculate_pnl_percent(pos, current_price)
            if pnl_percent >= self.config.profit.single_order_profit:
                await self._close_position(pos)
                actions.append(f"SINGLE_TP_BUY_{pos.id}")

        for pos in self.sell_positions[:]:
            pnl_percent = self._calculate_pnl_percent(pos, current_price)
            if pnl_percent >= self.config.profit.single_order_profit:
                await self._close_position(pos)
                actions.append(f"SINGLE_TP_SELL_{pos.id}")

    # 2. Pair Global Profit
    if self.config.profit.pair_global_profit > 0:
        total_pnl_percent = self._calculate_total_pnl_percent(current_price)
        if total_pnl_percent >= self.config.profit.pair_global_profit:
            await self._close_all_positions()
            actions.append("PAIR_GLOBAL_TP")

    # 3. Global Profit (daily target)
    if self.config.profit.global_profit > 0:
        realized_pnl = self.performance.realized_pnl
        if realized_pnl >= self.config.profit.global_profit:
            actions.append("GLOBAL_PROFIT_HIT")
            self._should_stop = True

    # 4. Max Loss (daily limit)
    if self.config.profit.max_loss > 0:
        realized_pnl = self.performance.realized_pnl
        if realized_pnl <= -self.config.profit.max_loss:
            actions.append("MAX_LOSS_HIT")
            self._should_stop = True

    return actions
```

---

## 5. API ENDPOINTS

### 5.1 Health & Info

```
GET /health
Response: {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 3600,
    "sessions": {"total": 5, "running": 3}
}

GET /info
Response: {
    "name": "Hedging Grid Robot",
    "version": "1.0.0",
    "strategy": "GRID_HEDGING",
    "description": "Grid hedging strategy with SMA/SAR/CCI indicators",
    "supportedPairs": ["BTCUSDT", "ETHUSDT", ...],
    "supportedExchanges": ["bitget"],
    "capabilities": {
        "spot": false,
        "futures": true,
        "margin": false,
        "grid": true,
        "hedge": true,
        "martingale": true
    },
    "defaultSettings": {...},
    "customSettingsSchema": {...}
}
```

### 5.2 User Management

```
POST /api/v1/users
Body: {
    "userId": "user123",
    "userBotId": "bot456",
    "exchange": {
        "name": "bitget",
        "apiKey": "...",
        "apiSecret": "...",
        "passphrase": "...",
        "isDemo": true
    },
    "settings": {
        "tradingPair": "BTCUSDT",
        "leverage": 10,
        "customSettings": {
            "multiplier": 1.5,
            "spacePercent": 0.5,
            "smaPeriod": 7,
            "useSmaEntry": true,
            "cciPeriod": 20,
            "singleOrderProfit": 3.0,
            "pairGlobalProfit": 1.0,
            "globalProfit": 100,
            "maxLoss": 50,
            ...
        }
    },
    "webhookUrl": "https://hema.azro.uz/api/webhooks/bot/hedge-bot-001",
    "webhookSecret": "..."
}

POST /api/v1/users/{user_id}/start
POST /api/v1/users/{user_id}/stop
GET /api/v1/users/{user_id}/status
DELETE /api/v1/users/{user_id}
```

---

## 6. WEBHOOK EVENTS

### 6.1 Status Update Format

```json
{
    "event": "status_update",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "data": {
        "userId": "user123",
        "userBotId": "bot456",
        "symbol": "BTCUSDT",
        "currentPrice": 42000.50,
        "indicators": {
            "sma": 41950.25,
            "sar": 42100.00,
            "cci": 75.5,
            "signal": "BUY"
        },
        "balance": 1000.00,
        "positions": {
            "buy": [
                {
                    "price": 41500.00,
                    "lot": 0.001,
                    "orderId": "123456",
                    "gridLevel": 1,
                    "pnl": 0.50,
                    "pnlPercent": 1.2,
                    "openedAt": "2024-01-15T10:00:00.000Z"
                },
                {
                    "price": 41000.00,
                    "lot": 0.0015,
                    "orderId": "123457",
                    "gridLevel": 2,
                    "pnl": 1.50,
                    "pnlPercent": 3.6,
                    "openedAt": "2024-01-15T10:05:00.000Z"
                }
            ],
            "sell": [
                {
                    "price": 42500.00,
                    "lot": 0.001,
                    "orderId": "123458",
                    "gridLevel": 1,
                    "pnl": -0.50,
                    "pnlPercent": -1.2,
                    "openedAt": "2024-01-15T10:02:00.000Z"
                }
            ],
            "buyCount": 2,
            "sellCount": 1,
            "buyPnl": 2.00,
            "sellPnl": -0.50,
            "totalPnl": 1.50
        },
        "grid": {
            "multiplier": 1.5,
            "spacePercent": 0.5,
            "maxBuyOrders": 20,
            "maxSellOrders": 20
        },
        "profit": {
            "singleOrderProfit": 3.0,
            "pairGlobalProfit": 1.0,
            "globalProfit": 100.0,
            "maxLoss": 50.0
        },
        "performance": {
            "totalTrades": 50,
            "winningTrades": 35,
            "losingTrades": 15,
            "winRate": 70.0,
            "totalPnL": 150.75,
            "unrealizedPnL": 1.50
        },
        "settings": {
            "leverage": 10,
            "timeframe": "1H",
            "baseLot": 0.001,
            "useSmaEntry": true,
            "cciPeriod": 20
        },
        "runtime": {
            "tick": 1234,
            "uptime": 3600,
            "startedAt": "2024-01-15T09:30:00.000Z",
            "lastTradeAt": "2024-01-15T10:05:00.000Z"
        },
        "tick": 1234
    }
}
```

### 6.2 Global Limit Hit Event

```json
{
    "event": "global_limit_hit",
    "timestamp": "2024-01-15T12:00:00.000Z",
    "data": {
        "userId": "user123",
        "userBotId": "bot456",
        "symbol": "BTCUSDT",
        "totalPnl": 100.50,
        "limitType": "PROFIT",
        "limitValue": 100.0,
        "positionsClosed": 5,
        "message": "Daily profit target reached: $100.50"
    }
}
```

---

## 7. ANIQLANGAN MUAMMOLAR

### 7.1 KRITIK

#### M1: Pozitsiya Sync Yo'q
**Fayl:** `strategy.py`, `robot.py`

```python
# HOZIRGI KOD (MUAMMO)
class HedgingStrategy:
    def __init__(self):
        self.buy_positions = []   # Faqat memory'da!
        self.sell_positions = []
```

**YECHIM:**
```python
# strategy.py

async def sync_positions_from_exchange(self, api: BitgetClient) -> bool:
    """Sync local state with exchange positions."""
    try:
        # Get all open positions from exchange
        exchange_positions = await api.get_positions(self.symbol)

        # Reset local state
        self.buy_positions = []
        self.sell_positions = []

        for pos in exchange_positions:
            position = GridPosition(
                id=pos['positionId'],
                side=pos['holdSide'],  # 'long' or 'short'
                entry_price=float(pos['averageOpenPrice']),
                lot=float(pos['total']),
                level=self._detect_grid_level(float(pos['averageOpenPrice'])),
                order_id=pos['positionId'],
                timestamp=time.time()
            )

            if pos['holdSide'] == 'long':
                self.buy_positions.append(position)
            else:
                self.sell_positions.append(position)

        logger.info(
            f"Position sync complete: "
            f"{len(self.buy_positions)} buys, "
            f"{len(self.sell_positions)} sells"
        )
        return True

    except Exception as e:
        logger.error(f"Position sync failed: {e}")
        return False

def _detect_grid_level(self, entry_price: float) -> int:
    """Detect grid level based on entry price distance."""
    # Calculate distance from current price
    distance_percent = abs(entry_price - self.last_price) / self.last_price * 100

    # Find matching level
    cumulative = 0
    for i, level in enumerate(self.config.grid.levels):
        cumulative += level.percent
        if distance_percent <= cumulative:
            return i

    return len(self.config.grid.levels) - 1
```

---

#### M2: Grid Level Overlap Tekshirilmaydi
**Fayl:** `config.py`

```python
# HOZIRGI KOD (MUAMMO)
# Grid levels bir-birini qoplashi mumkin
SPACE_PERCENT=0.5
SPACE1_PERCENT=0.3   # Bu SPACE_PERCENT dan kichik!
```

**YECHIM:**
```python
# config.py

def validate_grid_levels(self) -> List[str]:
    """Validate grid level configuration."""
    errors = []

    # Check each level is greater than previous
    prev_percent = 0
    for i, level in enumerate(self.levels):
        if level.percent <= prev_percent:
            errors.append(
                f"Grid level {i+1} ({level.percent}%) must be greater than "
                f"level {i} ({prev_percent}%)"
            )
        prev_percent = level.percent

        if level.max_orders <= 0:
            errors.append(f"Grid level {i+1} max_orders must be positive")

        if level.lot_size <= 0:
            errors.append(f"Grid level {i+1} lot_size must be positive")

    return errors
```

---

#### M3: Balance 30 Tickda Bir Yangilanadi
**Fayl:** `robot.py`

```python
# HOZIRGI KOD (MUAMMO)
if self._tick_count % 30 == 0:
    self.balance = await self.api.get_balance(...)
# 30 soniya ichida pozitsiya sizing xato bo'lishi mumkin!
```

**YECHIM:**
```python
# robot.py

# Balance yangilanish chastotasini oshirish
BALANCE_UPDATE_INTERVAL = 5  # 5 tickda 1 marta

async def _tick(self):
    # Update balance more frequently
    if self._tick_count % BALANCE_UPDATE_INTERVAL == 0:
        try:
            self.balance = await self.api.get_balance(self.symbol)
        except Exception as e:
            logger.warning(f"Balance update failed: {e}")
            # Use cached balance

    # Before opening position, verify balance is sufficient
    if can_open:
        required_margin = self._calculate_required_margin(lot_size)
        if self.balance < required_margin * 1.2:  # 20% buffer
            logger.warning("Insufficient balance for new position")
            can_open = False
```

---

#### M4: Global Limit Hit - Pozitsiyalar Yopilmaydi
**Fayl:** `robot.py`, `strategy.py`

```python
# HOZIRGI KOD (MUAMMO)
if realized_pnl >= self.config.profit.global_profit:
    actions.append("GLOBAL_PROFIT_HIT")
    self._should_stop = True
    # Pozitsiyalar yopilMAYDI!
```

**YECHIM:**
```python
# strategy.py

async def check_global_limits(self, current_price: float) -> Optional[str]:
    """Check global profit/loss limits and close all if hit."""

    # Global Profit
    if self.config.profit.global_profit > 0:
        realized_pnl = self.performance.realized_pnl
        if realized_pnl >= self.config.profit.global_profit:
            logger.info(f"Global profit target reached: ${realized_pnl:.2f}")

            # Close ALL positions
            closed_count = await self._close_all_positions_with_reason("GLOBAL_PROFIT")

            # Send webhook
            await self._send_global_limit_webhook(
                limit_type="PROFIT",
                limit_value=self.config.profit.global_profit,
                total_pnl=realized_pnl,
                positions_closed=closed_count
            )

            return "GLOBAL_PROFIT_HIT"

    # Max Loss
    if self.config.profit.max_loss > 0:
        realized_pnl = self.performance.realized_pnl
        if realized_pnl <= -self.config.profit.max_loss:
            logger.warning(f"Max loss limit reached: ${realized_pnl:.2f}")

            # Close ALL positions
            closed_count = await self._close_all_positions_with_reason("MAX_LOSS")

            # Send webhook
            await self._send_global_limit_webhook(
                limit_type="LOSS",
                limit_value=self.config.profit.max_loss,
                total_pnl=realized_pnl,
                positions_closed=closed_count
            )

            return "MAX_LOSS_HIT"

    return None
```

---

### 7.2 YUQORI PRIORITET

#### M5: Martingale Limitsiz

```python
# HOZIRGI KOD (MUAMMO)
lot = last_lot * self.config.grid.multiplier
# 10 pozitiyadа: 0.001 × 1.5^10 = 0.057 (57x!)
```

**YECHIM:**
```python
# strategy.py

MAX_MARTINGALE_MULTIPLIER = 10  # Max 10x from base lot

def _calculate_lot(self, position_count: int) -> float:
    if self.config.grid.multiplier > 0:
        # Calculate with cap
        multiplier = self.config.grid.multiplier ** position_count
        multiplier = min(multiplier, MAX_MARTINGALE_MULTIPLIER)
        lot = self.config.grid.base_lot * multiplier
    else:
        level = self.get_current_grid_level_by_count(position_count)
        lot = self.config.grid.levels[level].lot_size

    # Additional safety: check against account equity
    max_allowed = self.balance * 0.1  # Max 10% of balance per position
    lot = min(lot, max_allowed / self.leverage / self.last_price)

    return max(self.config.grid.min_lot, min(self.config.grid.max_lot, lot))
```

---

#### M6: Indicator State Persistence

```python
# indicators.py

class ParabolicSAR:
    def save_state(self) -> dict:
        return {
            "af": self.af,
            "ep": self.ep,
            "sar": self.sar,
            "trend": self.trend
        }

    def load_state(self, state: dict):
        self.af = state.get("af", self.af_start)
        self.ep = state.get("ep")
        self.sar = state.get("sar")
        self.trend = state.get("trend")

class CCIIndicator:
    def save_state(self) -> dict:
        return {"history": self.history[-50:]}  # Last 50 values

    def load_state(self, state: dict):
        self.history = state.get("history", [])
```

---

#### M7: Candle Caching

```python
# robot.py

class CandleCache:
    def __init__(self, symbol: str, timeframe: str, max_size: int = 200):
        self.symbol = symbol
        self.timeframe = timeframe
        self.candles: List[dict] = []
        self.max_size = max_size
        self.last_fetch_time = 0

    async def get_candles(self, api: BitgetClient, count: int = 100) -> List[dict]:
        """Get candles with caching."""
        now = time.time()

        # Fetch new candles if cache is stale (> 1 second old)
        if now - self.last_fetch_time > 1:
            try:
                # Only fetch last 5 candles
                new_candles = await api.get_candles(
                    self.symbol,
                    self.timeframe,
                    limit=5
                )

                # Merge with cache
                self._merge_candles(new_candles)
                self.last_fetch_time = now

            except Exception as e:
                logger.warning(f"Candle fetch failed, using cache: {e}")

        return self.candles[-count:]

    def _merge_candles(self, new_candles: List[dict]):
        """Merge new candles into cache."""
        for candle in new_candles:
            # Find existing candle by timestamp
            existing = next(
                (c for c in self.candles if c['timestamp'] == candle['timestamp']),
                None
            )

            if existing:
                # Update existing (for current candle)
                existing.update(candle)
            else:
                # Add new
                self.candles.append(candle)

        # Sort by timestamp
        self.candles.sort(key=lambda x: x['timestamp'])

        # Trim to max size
        if len(self.candles) > self.max_size:
            self.candles = self.candles[-self.max_size:]
```

---

### 7.3 O'RTACHA PRIORITET

#### M8: LWMA Formula To'g'rilash

```python
# indicators.py - HOZIRGI KOD
weights = list(range(1, self.period + 1))  # 1,2,3,...N

# YECHIM - True LWMA
def calculate_lwma(self, candles: List[dict]) -> float:
    """
    Linear Weighted Moving Average.
    Newest data has highest weight.
    """
    prices = [self._weighted_price(c) for c in candles[-self.period:]]

    # Weights: N, N-1, N-2, ..., 1 (newest has highest)
    weights = list(range(self.period, 0, -1))

    weighted_sum = sum(p * w for p, w in zip(prices, weights))
    weight_total = sum(weights)

    return weighted_sum / weight_total
```

---

#### M9: Admin Auth

```python
# server.py

async def verify_admin(x_admin_key: str = Header(None)):
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(401, "Unauthorized")
    return True

@app.get("/api/v1/admin/sessions")
async def get_sessions(auth: bool = Depends(verify_admin)):
    return session_manager.get_all_sessions()
```

---

#### M10: Webhook Queue Limit

```python
# webhook_client.py

MAX_QUEUE_SIZE = 1000

class WebhookClient:
    def __init__(self, ...):
        self._event_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    async def send_event(self, event_type: str, data: dict):
        try:
            await asyncio.wait_for(
                self._event_queue.put({"event": event_type, "data": data}),
                timeout=0.5
            )
        except asyncio.TimeoutError:
            logger.warning(f"Queue full, dropping {event_type} event")
```

---

## 8. RSI BOT BILAN FARQLAR

| Xususiyat | RSI Bot | Hedging Bot |
|-----------|---------|-------------|
| **Strategiya** | RSI crossover | SMA/SAR + CCI |
| **Pozitsiyalar** | Bir tomonga | Ikki tomonlama |
| **Grid** | Oddiy averaging | 4-darajali grid |
| **TP Logic** | Bitta TP (averaging) | Single + Pair + Global |
| **Indikatorlar** | RSI | SMA, SAR, CCI |
| **Murakkablik** | O'rtacha | Yuqori |
| **Risk** | O'rtacha (martingale) | Yuqori (ikki tomonlama martingale) |

---

## 9. XULOSA

### Umumiy Baho: 6/10

| Aspekt | Baho | Izoh |
|--------|------|------|
| Arxitektura | 8/10 | Yaxshi tuzilgan |
| Trading Logic | 7/10 | Grid logic to'g'ri |
| Indicators | 6/10 | SAR yaxshi, LWMA simplified |
| Error Handling | 5/10 | Circuit breaker yo'q |
| Risk Management | 4/10 | Martingale limitsiz |
| Security | 4/10 | Admin auth yo'q |
| Testing | 2/10 | Testlar yo'q |
| Production Ready | 5/10 | Hardening kerak |

### Birinchi Navbatda Qilish Kerak

1. **Pozitsiya Sync** - Exchange bilan sinxronizatsiya
2. **Martingale Limit** - MAX_MARTINGALE_MULTIPLIER qo'shish
3. **Grid Validation** - Level overlap tekshirish
4. **Global Limit Fix** - Pozitsiyalarni yopish
5. **Balance Update** - Chastotani oshirish (5 tick)
