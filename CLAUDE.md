# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# CLI mode (single user)
python run.py
python run.py --symbol ETHUSDT --leverage 20 --debug
python run.py --demo  # Paper trading mode

# Server mode (multi-user HEMA integration)
python run_server.py
python run_server.py --host 0.0.0.0 --port 8082 --reload --debug

# Docker
docker-compose up -d                    # Production
docker-compose --profile dev up         # Development with auto-reload
```

No test suite exists in this project.

## Architecture

Grid hedging trading robot for Bitget Futures, ported from MQL4 Expert Advisor.

### Component Flow

```
FastAPI Server (server.py)
    │
    ▼
SessionManager (session_manager.py) ── Singleton, manages all user sessions
    │
    ├── HedgingRobotWithWebhook ─────── Extends robot with webhook events
    │       │
    │       ▼
    │   HedgingRobot (robot.py) ─────── Main async tick loop, state machine
    │       │
    │       ▼
    │   HedgingStrategy (strategy.py)── Grid logic, signals, profit taking
    │       │
    │       ▼
    │   Indicators (indicators.py) ──── SMA, Parabolic SAR, CCI
    │       │
    │       ▼
    │   BitgetClient (api_client.py) ── REST API with HMAC-SHA256 auth
    │
    └── WebhookClient (webhook_client.py) ── Async queue-based event sender
```

### Key Patterns

- **Async throughout**: asyncio tasks, aiohttp sessions, queue-based webhooks
- **Dataclass configs**: All configuration in `config.py` as dataclasses
- **State machine**: RobotState enum (IDLE → STARTING → RUNNING → STOPPING → STOPPED)
- **4-level grid**: SPACE/SPACE1/SPACE2/SPACE3 with configurable distances and order counts

### Trading Logic (strategy.py)

**Entry signals:**
- SMA/Parabolic SAR: BUY when SAR > SMA, SELL when SAR < SMA
- CCI: BUY when CCI crosses above CCI_MAX, SELL when CCI crosses below CCI_MIN

**Grid orders:** When price moves against position by grid distance %, add new order with martingale lot sizing (or fixed lots if MULTIPLIER=0)

**Profit taking priority:**
1. Single order hits SINGLE_ORDER_PROFIT → close all
2. Combined buy+sell profit hits PAIR_GLOBAL_PROFIT → close all
3. Global profit/loss limits → stop trading

### API Endpoints

User lifecycle: `POST /api/v1/users` → `POST .../start` → `GET .../status` → `POST .../stop` → `DELETE`

Admin (requires `X-Admin-Key` header): `/api/v1/admin/sessions`, `/api/v1/admin/resources`, `/api/v1/admin/close-positions/{id}`

### Webhook Events

Events sent to HEMA: `trade_opened`, `trade_closed`, `status_update` (every 5 ticks), `status_changed`, `error_occurred`, `balance_warning`, `global_limit_hit`

## Configuration

All settings via `.env` file (see `.env.example`). Key groups:
- **Grid**: MULTIPLIER, SPACE_PERCENT/ORDERS/LOTS for each of 4 levels
- **Entry**: USE_SMA_SAR, SMA_PERIOD, SAR_AF/MAX, CCI_PERIOD/MAX/MIN, TIMEFRAME
- **Profit**: SINGLE_ORDER_PROFIT, PAIR_GLOBAL_PROFIT, GLOBAL_PROFIT, MAX_LOSS
