"""
Hedging Grid Robot - FastAPI Server

HEMA platformasi bilan REST API integratsiyasi
"""

import asyncio
import os
import logging
import time
import hashlib
import hmac
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil

from .session_manager import get_session_manager, SessionStatus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#                               SERVER CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

BOT_ID = os.getenv("BOT_ID", "hedging-grid-bot")
BOT_NAME = os.getenv("BOT_NAME", "Hedging Grid Robot")
BOT_VERSION = os.getenv("BOT_VERSION", "1.0.0")
BOT_SECRET = os.getenv("BOT_SECRET", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")  # M9 fix - Admin auth

START_TIME = datetime.utcnow()


# ═══════════════════════════════════════════════════════════════════════════════
#                               REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ExchangeCredentials(BaseModel):
    """Exchange credentials"""
    name: str = "bitget"
    apiKey: str
    apiSecret: str
    passphrase: Optional[str] = None
    isDemo: bool = True


class TradingSettings(BaseModel):
    """Trading settings from HEMA"""
    tradingPair: str = "BTCUSDT"
    tradeAmount: float = 0.01
    takeProfit: float = 3.0
    stopLoss: float = 0.0
    maxConcurrentTrades: int = 10
    leverage: int = 10
    customSettings: Optional[Dict[str, Any]] = None


class RegisterUserRequest(BaseModel):
    """User registration request"""
    userId: str
    userBotId: str
    exchange: ExchangeCredentials
    settings: TradingSettings
    webhookUrl: str
    webhookSecret: str


class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool = True
    message: str = ""
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error: str
    code: str = "ERROR"


# ═══════════════════════════════════════════════════════════════════════════════
#                               BACKGROUND TASKS
# ═══════════════════════════════════════════════════════════════════════════════

# G10 fix - Background cleanup task flag
_cleanup_task: Optional[asyncio.Task] = None


async def _cleanup_loop():
    """G10 fix - Background task for session cleanup"""
    session_manager = get_session_manager()
    while True:
        try:
            await asyncio.sleep(3600)  # Har 1 soatda
            await session_manager.cleanup_old_sessions(max_age_hours=24)
            logger.debug("Session cleanup completed")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """G10 fix - Lifespan context manager for cleanup task"""
    global _cleanup_task
    # Startup
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("Session cleanup task started")

    yield

    # Shutdown
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    logger.info("Session cleanup task stopped")


# ═══════════════════════════════════════════════════════════════════════════════
#                               FASTAPI APP
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=BOT_NAME,
    description="Grid Hedging Trading Robot for HEMA Platform",
    version=BOT_VERSION,
    lifespan=lifespan  # G10 fix
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
#                               EXCEPTION HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

from fastapi.responses import JSONResponse


# Error code mapping for HEMA compatibility
ERROR_CODE_MAP = {
    404: "USER_NOT_FOUND",
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    409: "CONFLICT",
    500: "INTERNAL_ERROR",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom exception handler that returns errors in HEMA-compatible format.

    HEMA expects: {"error": {"code": "...", "message": "..."}}
    FastAPI default: {"detail": "..."}
    """
    error_code = ERROR_CODE_MAP.get(exc.status_code, "ERROR")

    # Check if detail contains specific error hints
    detail_str = str(exc.detail).lower()
    if "not found" in detail_str or "not registered" in detail_str:
        error_code = "USER_NOT_FOUND"
    elif "not running" in detail_str or "already stopped" in detail_str:
        error_code = "NOT_RUNNING"
    elif "already running" in detail_str:
        error_code = "ALREADY_RUNNING"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc.detail)
            }
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
#                               AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

# N1 fix - Development mode flag
ALLOW_INSECURE = os.getenv("ALLOW_INSECURE", "false").lower() == "true"


def verify_signature(timestamp: str, payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC signature"""
    if not secret:
        # N1 fix - secret majburiy
        raise ValueError("Secret key is required for signature verification")

    message = f"{timestamp}.{payload}"
    expected = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def verify_request(request: Request):
    """Verify incoming request from HEMA"""
    # N1 fix - BOT_SECRET majburiy (development mode dan tashqari)
    if not BOT_SECRET:
        if ALLOW_INSECURE:
            logger.warning("SECURITY WARNING: BOT_SECRET not configured, skipping verification!")
            return True
        else:
            raise HTTPException(
                status_code=500,
                detail="Server misconfigured: BOT_SECRET not set. Set ALLOW_INSECURE=true for development."
            )

    timestamp = request.headers.get("X-Webhook-Timestamp", "")
    signature = request.headers.get("X-Webhook-Signature", "")

    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing authentication headers")

    # Check timestamp (5 minute window)
    try:
        ts = int(timestamp)
        if abs(time.time() * 1000 - ts) > 5 * 60 * 1000:
            raise HTTPException(status_code=401, detail="Request expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    body = await request.body()
    if not verify_signature(timestamp, body.decode(), signature, BOT_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    return True


# ═══════════════════════════════════════════════════════════════════════════════
#                               HEALTH & INFO ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

async def _health_response():
    """Health check response data"""
    uptime = int((datetime.utcnow() - START_TIME).total_seconds())
    manager = get_session_manager()

    return {
        "status": "healthy",
        "version": BOT_VERSION,
        "uptime": uptime,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "activeSessions": manager.active_sessions,
        "totalSessions": manager.total_sessions
    }


async def _info_response():
    """Bot info response data - HEMA format"""
    return {
        "id": BOT_ID,
        "name": BOT_NAME,
        "version": BOT_VERSION,
        "strategy": "GRID_HEDGING",
        "description": "Grid Hedging strategiyasi asosida ishlaydigan trading robot. Martingale lot sizing va SMA/SAR/CCI entry signallari bilan.",
        "author": "HEMA",
        "exchange": "bitget",
        "supportedPairs": [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
            "DOGEUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
            "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "UNIUSDT", "APTUSDT"
        ],
        "supportedExchanges": ["bitget"],
        "minTradeAmount": 10,
        "maxTradeAmount": 10000,
        "defaultSettings": {
            "tradingPair": "BTCUSDT",
            "leverage": 10,
            "tradeAmount": 100,
            "takeProfit": 3.0,
            "stopLoss": 0,
            "maxConcurrentTrades": 10
        },
        # HEMA-compatible configSchema format
        # type: 'number' | 'string' | 'boolean' | 'select'
        # label instead of name
        "configSchema": {
            # Grid Settings
            "multiplier": {
                "label": "Martingale Multiplier",
                "type": "number",
                "default": 1.5,
                "min": 0,
                "max": 5.0,
                "step": 0.1,
                "description": "Lot ko'paytirish koeffitsiyenti (0 = fixed lot)",
                "group": "Grid Settings"
            },
            "spacePercent": {
                "label": "Grid Space %",
                "type": "number",
                "default": 0.5,
                "min": 0.1,
                "max": 10.0,
                "step": 0.1,
                "description": "Grid Level 1 masofa (foizda)",
                "group": "Grid Settings"
            },
            "spaceOrders": {
                "label": "Grid Level 1 Orders",
                "type": "number",
                "default": 5,
                "min": 1,
                "max": 50,
                "step": 1,
                "description": "Grid Level 1 dagi orderlar soni",
                "group": "Grid Settings"
            },
            "space1Percent": {
                "label": "Grid Level 2 %",
                "type": "number",
                "default": 1.5,
                "min": 0.5,
                "max": 20.0,
                "step": 0.1,
                "description": "Grid Level 2 masofa (foizda)",
                "group": "Grid Settings"
            },
            "space2Percent": {
                "label": "Grid Level 3 %",
                "type": "number",
                "default": 3.0,
                "min": 1.0,
                "max": 30.0,
                "step": 0.5,
                "description": "Grid Level 3 masofa (foizda)",
                "group": "Grid Settings"
            },
            "space3Percent": {
                "label": "Grid Level 4 %",
                "type": "number",
                "default": 5.0,
                "min": 2.0,
                "max": 50.0,
                "step": 0.5,
                "description": "Grid Level 4 masofa (foizda)",
                "group": "Grid Settings"
            },
            # Entry Settings
            "useSmaSar": {
                "label": "Use SMA/SAR Entry",
                "type": "boolean",
                "default": True,
                "description": "SMA/Parabolic SAR signallarini ishlatish",
                "group": "Entry Settings"
            },
            "smaPeriod": {
                "label": "SMA Period",
                "type": "number",
                "default": 7,
                "min": 3,
                "max": 100,
                "step": 1,
                "description": "SMA indikator davri",
                "group": "Entry Settings"
            },
            "sarAf": {
                "label": "SAR Acceleration",
                "type": "number",
                "default": 0.1,
                "min": 0.01,
                "max": 0.5,
                "step": 0.01,
                "description": "Parabolic SAR acceleration factor",
                "group": "Entry Settings"
            },
            "sarMax": {
                "label": "SAR Maximum",
                "type": "number",
                "default": 0.8,
                "min": 0.1,
                "max": 1.0,
                "step": 0.1,
                "description": "Parabolic SAR maksimal AF",
                "group": "Entry Settings"
            },
            "cciPeriod": {
                "label": "CCI Period",
                "type": "number",
                "default": 0,
                "min": 0,
                "max": 100,
                "step": 1,
                "description": "CCI indikator davri (0 = o'chirilgan)",
                "group": "Entry Settings"
            },
            "cciMax": {
                "label": "CCI Max Level",
                "type": "number",
                "default": 100,
                "min": 50,
                "max": 200,
                "step": 10,
                "description": "CCI yuqori signal darajasi",
                "group": "Entry Settings"
            },
            "cciMin": {
                "label": "CCI Min Level",
                "type": "number",
                "default": -100,
                "min": -200,
                "max": -50,
                "step": 10,
                "description": "CCI past signal darajasi",
                "group": "Entry Settings"
            },
            "timeframe": {
                "label": "Timeframe",
                "type": "select",
                "default": "1H",
                "options": [
                    {"value": "1m", "label": "1 Minute"},
                    {"value": "5m", "label": "5 Minutes"},
                    {"value": "15m", "label": "15 Minutes"},
                    {"value": "30m", "label": "30 Minutes"},
                    {"value": "1H", "label": "1 Hour"},
                    {"value": "4H", "label": "4 Hours"},
                    {"value": "1D", "label": "1 Day"}
                ],
                "description": "Signal timeframe",
                "group": "Entry Settings"
            },
            "reverseOrder": {
                "label": "Reverse Signals",
                "type": "boolean",
                "default": False,
                "description": "Signal yo'nalishini teskari qilish",
                "group": "Entry Settings"
            },
            # Profit Settings
            "singleOrderProfit": {
                "label": "Single Order Profit",
                "type": "number",
                "default": 3.0,
                "min": 0.1,
                "max": 1000,
                "step": 0.5,
                "description": "Bitta order uchun profit target (USDT)",
                "group": "Profit Settings"
            },
            "pairGlobalProfit": {
                "label": "Pair Global Profit",
                "type": "number",
                "default": 1.0,
                "min": 0,
                "max": 1000,
                "step": 0.5,
                "description": "Buy+Sell juftlik profit target (USDT)",
                "group": "Profit Settings"
            },
            "globalProfit": {
                "label": "Daily Profit Target",
                "type": "number",
                "default": 0,
                "min": 0,
                "max": 10000,
                "step": 10,
                "description": "Kunlik profit target (0 = cheksiz)",
                "group": "Profit Settings"
            },
            "maxLoss": {
                "label": "Max Loss",
                "type": "number",
                "default": 0,
                "min": -10000,
                "max": 0,
                "step": 10,
                "description": "Maksimal zarar chegarasi (0 = cheksiz)",
                "group": "Profit Settings"
            },
            # Position Sizing
            "baseLot": {
                "label": "Base Lot Size",
                "type": "number",
                "default": 0.01,
                "min": 0.001,
                "max": 10.0,
                "step": 0.001,
                "description": "Boshlang'ich lot hajmi",
                "group": "Position Sizing"
            },
            "leverage": {
                "label": "Leverage",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 125,
                "step": 1,
                "description": "Trading leverage",
                "group": "Position Sizing"
            },
            "tradesPerDay": {
                "label": "Trades Per Day",
                "type": "number",
                "default": 99,
                "min": 1,
                "max": 999,
                "step": 1,
                "description": "Kunlik maksimal savdolar soni",
                "group": "Risk Management"
            }
        },
        "capabilities": {
            "spot": False,
            "futures": True,
            "margin": False
        },
        "riskWarning": "Bu robot grid hedging va martingale strategiyasini ishlatadi. Katta yo'qotishlarga olib kelishi mumkin. Ehtiyotkorlik bilan foydalaning.",
        "minBalance": 100,
        "recommendedBalance": 500
    }


# Root level endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return await _health_response()


@app.get("/info")
async def bot_info():
    """Bot information endpoint - root level"""
    return await _info_response()


# API versioned endpoints (for HEMA compatibility)
@app.get("/api/v1/health")
async def health_check_v1():
    """Health check endpoint - API v1"""
    return await _health_response()


@app.get("/api/v1/info")
async def bot_info_v1():
    """Bot info endpoint - API v1 (called by HEMA when adding bot)"""
    return await _info_response()


# ═══════════════════════════════════════════════════════════════════════════════
#                               USER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/users", response_model=SuccessResponse)
async def register_user(request: Request, body: RegisterUserRequest):
    """
    Register a new user

    HEMA calls this when a user enables this bot
    """
    await verify_request(request)

    manager = get_session_manager()

    try:
        session = await manager.register_user(
            user_id=body.userId,
            user_bot_id=body.userBotId,
            exchange={
                "apiKey": body.exchange.apiKey,
                "apiSecret": body.exchange.apiSecret,
                "passphrase": body.exchange.passphrase,
                "isDemo": body.exchange.isDemo
            },
            settings={
                "tradingPair": body.settings.tradingPair,
                "tradeAmount": body.settings.tradeAmount,
                "takeProfit": body.settings.takeProfit,
                "stopLoss": body.settings.stopLoss,
                "maxConcurrentTrades": body.settings.maxConcurrentTrades,
                "leverage": body.settings.leverage,
                "customSettings": body.settings.customSettings or {}
            },
            webhook_url=body.webhookUrl,
            webhook_secret=body.webhookSecret
        )

        return SuccessResponse(
            message="User registered successfully",
            data=session.to_dict()
        )

    except Exception as e:
        logger.error(f"Failed to register user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/users/{user_id}/start", response_model=SuccessResponse)
async def start_trading(request: Request, user_id: str):
    """Start trading for a user"""
    await verify_request(request)

    manager = get_session_manager()

    try:
        session = await manager.start_trading(user_id)
        return SuccessResponse(
            message="Trading started",
            data=session.to_dict()
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/users/{user_id}/close-positions", response_model=SuccessResponse)
async def close_all_positions(request: Request, user_id: str):
    """Close all open positions for a user (without stopping the bot)"""
    await verify_request(request)

    manager = get_session_manager()
    session = manager.get_session(user_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    if not session.robot or session.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Robot not running")

    try:
        # Use the new method that sends proper webhooks
        await session.robot.close_all_positions_manually(reason="MANUAL_CLOSE")

        return SuccessResponse(
            message="All positions closed",
            data={
                "buy_closed": len(session.robot.strategy.buy_positions) == 0,
                "sell_closed": len(session.robot.strategy.sell_positions) == 0
            }
        )
    except Exception as e:
        logger.error(f"Failed to close positions for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/users/{user_id}/stop", response_model=SuccessResponse)
async def stop_trading(request: Request, user_id: str):
    """Stop trading for a user"""
    await verify_request(request)

    manager = get_session_manager()

    try:
        session = await manager.stop_trading(user_id)
        return SuccessResponse(
            message="Trading stopped",
            data=session.to_dict()
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/users/{user_id}/status", response_model=SuccessResponse)
async def get_user_status(request: Request, user_id: str):
    """Get user trading status"""
    await verify_request(request)

    manager = get_session_manager()

    try:
        status = await manager.get_status(user_id)
        return SuccessResponse(
            message="Status retrieved",
            data=status
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/users/{user_id}", response_model=SuccessResponse)
async def unregister_user(request: Request, user_id: str):
    """Unregister a user"""
    await verify_request(request)

    manager = get_session_manager()

    try:
        success = await manager.unregister_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        return SuccessResponse(message="User unregistered")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unregister user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/users/{user_id}/settings", response_model=SuccessResponse)
async def get_user_settings(request: Request, user_id: str):
    """
    Get user's current trading settings

    HEMA "Fetch from Server" tugmasi uchun - user ning barcha sozlamalarini qaytaradi
    """
    await verify_request(request)

    manager = get_session_manager()
    session = manager.get_session(user_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Asosiy sozlamalar
    settings_data = {
        # Trading pair va asosiy sozlamalar
        "tradingPair": session.trading_pair,
        "leverage": session.leverage,
        "isDemo": session.is_demo,

        # HEMA standart fieldlar (agar kerak bo'lsa)
        "tradeAmount": session.base_lot,  # Base lot size
        "takeProfit": session.single_order_profit,  # Single order profit target
        "stopLoss": abs(session.max_loss) if session.max_loss < 0 else 0,  # Max loss as positive
        "maxConcurrentTrades": session.space_orders + session.space1_orders + session.space2_orders + session.space3_orders,

        # Barcha custom sozlamalar (HEMA Settings Dialog uchun)
        "customSettings": {
            # Grid Settings
            "multiplier": session.multiplier,
            "spacePercent": session.space_percent,
            "spaceOrders": session.space_orders,
            "space1Percent": session.space1_percent,
            "space1Orders": session.space1_orders,
            "space2Percent": session.space2_percent,
            "space2Orders": session.space2_orders,
            "space3Percent": session.space3_percent,
            "space3Orders": session.space3_orders,

            # Entry Settings
            "useSmaSar": session.use_sma_sar,
            "smaPeriod": session.sma_period,
            "sarAf": session.sar_af,
            "sarMax": session.sar_max,
            "reverseOrder": session.reverse_order,
            "cciPeriod": session.cci_period,
            "cciMax": session.cci_max,
            "cciMin": session.cci_min,
            "timeframe": session.timeframe,

            # Profit Settings
            "singleOrderProfit": session.single_order_profit,
            "pairGlobalProfit": session.pair_global_profit,
            "globalProfit": session.global_profit,
            "maxLoss": session.max_loss,
            "tradesPerDay": session.trades_per_day,

            # Money/Position Settings
            "baseLot": session.base_lot,
            "minLot": session.min_lot,
            "maxLot": session.max_lot,
            "leverage": session.leverage,
        },

        # Session metadata
        "session": {
            "status": session.status.value,
            "userBotId": session.user_bot_id,
            "registeredAt": session.registered_at.isoformat() + "Z" if session.registered_at else None,
            "startedAt": session.started_at.isoformat() + "Z" if session.started_at else None,
        }
    }

    return SuccessResponse(
        message="Settings retrieved",
        data=settings_data
    )


# ═══════════════════════════════════════════════════════════════════════════════
#                               ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_admin(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    """
    Admin API key tekshirish (M9 fix)

    Header: X-Admin-Key: <admin_api_key>
    """
    if not ADMIN_API_KEY:
        # Admin key konfiguratsiya qilinmagan - server tayyor emas
        raise HTTPException(
            status_code=503,
            detail="Admin API sozlanmagan. ADMIN_API_KEY environment variable o'rnating."
        )

    if not x_admin_key:
        raise HTTPException(
            status_code=401,
            detail="X-Admin-Key header talab qilinadi"
        )

    if not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Noto'g'ri admin key"
        )

    return True


@app.get("/api/v1/admin/sessions")
async def list_sessions(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    """List all sessions (admin)"""
    await verify_admin(x_admin_key)

    manager = get_session_manager()

    sessions = []
    for session_key, session in manager._sessions.items():
        session_data = session.to_dict()
        session_data["session_key"] = session_key  # Session key ham qo'shish
        sessions.append(session_data)

    return {
        "total": len(sessions),
        "active": manager.active_sessions,
        "sessions": sessions,
        "bot_id_mappings": len(manager._sessions_by_bot_id)  # Mapping count
    }


@app.get("/api/v1/admin/resources")
async def get_resources(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    """Get resource usage"""
    await verify_admin(x_admin_key)

    process = psutil.Process()

    return {
        "cpu_percent": process.cpu_percent(),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "threads": process.num_threads(),
        "uptime": int((datetime.utcnow() - START_TIME).total_seconds())
    }


@app.post("/api/v1/admin/close-positions/{user_id}")
async def emergency_close_positions(
    user_id: str,
    x_admin_key: str = Header(None, alias="X-Admin-Key")
):
    """Emergency close all positions for a user"""
    await verify_admin(x_admin_key)

    manager = get_session_manager()
    session = manager.get_session(user_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Foydalanuvchi topilmadi: {user_id}"
        )

    if not session.robot:
        raise HTTPException(
            status_code=400,
            detail=f"Robot yaratilmagan. Status: {session.status.value}"
        )

    if session.status != SessionStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Robot ishlamayapti. Joriy status: {session.status.value}"
        )

    try:
        await session.robot._close_all_positions()
        return {
            "success": True,
            "message": "Barcha pozitsiyalar yopildi",
            "userId": user_id
        }
    except Exception as e:
        logger.error(f"Emergency close failed for {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Pozitsiyalarni yopishda xato: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                               DEBUG ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/debug/sessions")
async def debug_sessions():
    """Debug session info"""
    manager = get_session_manager()

    result = {
        "sessions": {},
        "bot_id_mappings": dict(manager._sessions_by_bot_id)
    }

    for session_key, session in manager._sessions.items():
        result["sessions"][session_key] = {
            "user_id": session.user_id,
            "user_bot_id": session.user_bot_id,
            "trading_pair": session.trading_pair,
            "status": session.status.value,
            "has_robot": session.robot is not None,
            "has_webhook": session.webhook_client is not None,
            "has_task": session.task is not None,
            "robot_state": session.robot.state.value if session.robot else None
        }

    return result
