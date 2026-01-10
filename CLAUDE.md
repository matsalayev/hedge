# Hedging Grid Robot

Grid Hedging Trading Robot for Bitget Futures with HEMA Platform Integration.

## Overview

This robot implements a grid hedging strategy ported from MQL4 Expert Advisor to Python. It supports:

- **Grid Trading**: Multiple orders at different price levels
- **Hedging**: Independent BUY and SELL positions
- **Martingale**: Progressive lot sizing
- **Entry Signals**: SMA/Parabolic SAR and CCI indicators
- **HEMA Integration**: Multi-user REST API with webhooks

## Project Structure

```
hedging_robot/
├── __init__.py          # Package exports
├── config.py            # Configuration (dataclasses)
├── indicators.py        # SMA, Parabolic SAR, CCI
├── strategy.py          # Grid hedging strategy
├── robot.py             # Main trading loop
├── api_client.py        # Bitget REST API client
├── session_manager.py   # Multi-user sessions
├── webhook_client.py    # HEMA webhooks
├── server.py            # FastAPI REST server
├── run.py               # CLI entry point
├── run_server.py        # Server entry point
├── Dockerfile           # Production image
├── docker-compose.yml   # Docker Compose
├── requirements.txt     # Dependencies
└── .env.example         # Configuration template
```

## Quick Start

### CLI Mode (Single User)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env

# Run robot
python run.py

# With options
python run.py --symbol ETHUSDT --leverage 20 --debug
```

### Server Mode (HEMA Integration)

```bash
# Run server
python run_server.py

# Or with Docker
docker-compose up -d
```

## Configuration

All settings are in `.env` file:

### Grid Settings
- `MULTIPLIER`: Martingale multiplier (0 = fixed lots)
- `SPACE_PERCENT`: Grid Level 1 distance (%)
- `SPACE_ORDERS`: Orders in Level 1
- `SPACE1_PERCENT`, `SPACE2_PERCENT`, `SPACE3_PERCENT`: Higher level distances

### Entry Settings
- `USE_SMA_SAR`: Enable SMA/Parabolic SAR entry
- `SMA_PERIOD`: SMA period (default: 7)
- `SAR_AF`, `SAR_MAX`: Parabolic SAR parameters
- `CCI_PERIOD`: CCI period (0 = disabled)
- `TIMEFRAME`: Candle timeframe (1m, 5m, 1H, etc.)

### Profit Settings
- `SINGLE_ORDER_PROFIT`: Profit target for single order (USDT)
- `PAIR_GLOBAL_PROFIT`: Combined profit target (USDT)
- `GLOBAL_PROFIT`: Daily profit target
- `MAX_LOSS`: Maximum loss limit

## API Endpoints

### Health & Info
- `GET /health` - Health check
- `GET /info` - Bot information and capabilities

### User Management
- `POST /api/v1/users` - Register user
- `POST /api/v1/users/{id}/start` - Start trading
- `POST /api/v1/users/{id}/stop` - Stop trading
- `GET /api/v1/users/{id}/status` - Get status
- `DELETE /api/v1/users/{id}` - Unregister user

### Admin
- `GET /api/v1/admin/sessions` - List all sessions
- `GET /api/v1/admin/resources` - Resource usage
- `POST /api/v1/admin/close-positions/{id}` - Emergency close

## Strategy Logic

### Entry Signals

**SMA/Parabolic SAR:**
- BUY: SAR > SMA
- SELL: SAR < SMA

**CCI:**
- BUY: CCI crosses above CCI_MAX
- SELL: CCI crosses below CCI_MIN

### Grid Levels

1. **Level 1**: `SPACE_PERCENT` distance, up to `SPACE_ORDERS` orders
2. **Level 2**: `SPACE1_PERCENT` distance, up to `SPACE1_ORDERS` orders
3. **Level 3**: `SPACE2_PERCENT` distance, up to `SPACE2_ORDERS` orders
4. **Level 4**: `SPACE3_PERCENT` distance, up to `SPACE3_ORDERS` orders

### Lot Sizing

- If `MULTIPLIER > 0`: `new_lot = last_lot * MULTIPLIER`
- If `MULTIPLIER = 0`: Fixed lots per level (`SPACE_LOTS`, etc.)

### Profit Taking

1. Single order: Close if profit >= `SINGLE_ORDER_PROFIT`
2. Pair profit: Close both sides if combined profit >= `PAIR_GLOBAL_PROFIT`
3. Global limits: Stop trading if profit >= `GLOBAL_PROFIT` or loss <= `MAX_LOSS`

## Development

```bash
# Run with debug
python run.py --debug

# Run server with auto-reload
python run_server.py --reload --debug

# Docker development
docker-compose --profile dev up
```

## Webhook Events

- `trade_opened` - Position opened
- `trade_closed` - Position closed
- `status_update` - Real-time status (every 5 ticks)
- `status_changed` - Session status changed
- `error_occurred` - Trading error
- `balance_warning` - Low balance warning

## Original EA Reference

Ported from: `EA Hedging Full (2).mq4`
Author: Aliasqar Islomov (Copyright 2025)
