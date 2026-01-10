"""
Hedging Grid Robot - FastAPI Server

HEMA platformasi bilan REST API integratsiyasi
"""

import os
import logging
import time
import hashlib
import hmac
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
#                               FASTAPI APP
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=BOT_NAME,
    description="Grid Hedging Trading Robot for HEMA Platform",
    version=BOT_VERSION
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
#                               AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

def verify_signature(timestamp: str, payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC signature"""
    if not secret:
        return True  # No secret configured, skip verification

    message = f"{timestamp}.{payload}"
    expected = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def verify_request(request: Request):
    """Verify incoming request from HEMA"""
    if not BOT_SECRET:
        return True

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
            "DOGEUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT"
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
        "customSettings": {
            # Grid Settings
            "multiplier": {
                "name": "Martingale Multiplier",
                "type": "float",
                "default": 1.5,
                "min": 0,
                "max": 5.0,
                "description": "Lot ko'paytirish koeffitsiyenti (0 = fixed lot)",
                "group": "Grid Settings"
            },
            "spacePercent": {
                "name": "Grid Space %",
                "type": "float",
                "default": 0.5,
                "min": 0.1,
                "max": 10.0,
                "description": "Grid Level 1 masofa (foizda)",
                "group": "Grid Settings"
            },
            "spaceOrders": {
                "name": "Grid Level 1 Orders",
                "type": "int",
                "default": 5,
                "min": 1,
                "max": 50,
                "description": "Grid Level 1 dagi orderlar soni",
                "group": "Grid Settings"
            },
            "space1Percent": {
                "name": "Grid Level 2 %",
                "type": "float",
                "default": 1.5,
                "min": 0.5,
                "max": 20.0,
                "description": "Grid Level 2 masofa (foizda)",
                "group": "Grid Settings"
            },
            "space2Percent": {
                "name": "Grid Level 3 %",
                "type": "float",
                "default": 3.0,
                "min": 1.0,
                "max": 30.0,
                "description": "Grid Level 3 masofa (foizda)",
                "group": "Grid Settings"
            },
            "space3Percent": {
                "name": "Grid Level 4 %",
                "type": "float",
                "default": 5.0,
                "min": 2.0,
                "max": 50.0,
                "description": "Grid Level 4 masofa (foizda)",
                "group": "Grid Settings"
            },
            # Entry Settings
            "useSmaSar": {
                "name": "Use SMA/SAR Entry",
                "type": "bool",
                "default": True,
                "description": "SMA/Parabolic SAR signallarini ishlatish",
                "group": "Entry Settings"
            },
            "smaPeriod": {
                "name": "SMA Period",
                "type": "int",
                "default": 7,
                "min": 3,
                "max": 100,
                "description": "SMA indikator davri",
                "group": "Entry Settings"
            },
            "sarAf": {
                "name": "SAR Acceleration",
                "type": "float",
                "default": 0.1,
                "min": 0.01,
                "max": 0.5,
                "description": "Parabolic SAR acceleration factor",
                "group": "Entry Settings"
            },
            "sarMax": {
                "name": "SAR Maximum",
                "type": "float",
                "default": 0.8,
                "min": 0.1,
                "max": 1.0,
                "description": "Parabolic SAR maksimal AF",
                "group": "Entry Settings"
            },
            "cciPeriod": {
                "name": "CCI Period",
                "type": "int",
                "default": 0,
                "min": 0,
                "max": 100,
                "description": "CCI indikator davri (0 = o'chirilgan)",
                "group": "Entry Settings"
            },
            "cciMax": {
                "name": "CCI Max Level",
                "type": "float",
                "default": 100,
                "min": 50,
                "max": 200,
                "description": "CCI yuqori signal darajasi",
                "group": "Entry Settings"
            },
            "cciMin": {
                "name": "CCI Min Level",
                "type": "float",
                "default": -100,
                "min": -200,
                "max": -50,
                "description": "CCI past signal darajasi",
                "group": "Entry Settings"
            },
            "timeframe": {
                "name": "Timeframe",
                "type": "select",
                "default": "1H",
                "options": ["1m", "5m", "15m", "30m", "1H", "4H", "1D"],
                "description": "Signal timeframe",
                "group": "Entry Settings"
            },
            "reverseOrder": {
                "name": "Reverse Signals",
                "type": "bool",
                "default": False,
                "description": "Signal yo'nalishini teskari qilish",
                "group": "Entry Settings"
            },
            # Profit Settings
            "singleOrderProfit": {
                "name": "Single Order Profit",
                "type": "float",
                "default": 3.0,
                "min": 0.1,
                "max": 1000,
                "description": "Bitta order uchun profit target (USDT)",
                "group": "Profit Settings"
            },
            "pairGlobalProfit": {
                "name": "Pair Global Profit",
                "type": "float",
                "default": 1.0,
                "min": 0,
                "max": 1000,
                "description": "Buy+Sell juftlik profit target (USDT)",
                "group": "Profit Settings"
            },
            "globalProfit": {
                "name": "Daily Profit Target",
                "type": "float",
                "default": 0,
                "min": 0,
                "max": 10000,
                "description": "Kunlik profit target (0 = cheksiz)",
                "group": "Profit Settings"
            },
            "maxLoss": {
                "name": "Max Loss",
                "type": "float",
                "default": 0,
                "min": -10000,
                "max": 0,
                "description": "Maksimal zarar chegarasi (0 = cheksiz)",
                "group": "Profit Settings"
            },
            # Position Sizing
            "baseLot": {
                "name": "Base Lot Size",
                "type": "float",
                "default": 0.01,
                "min": 0.001,
                "max": 10.0,
                "description": "Boshlang'ich lot hajmi",
                "group": "Position Sizing"
            },
            "leverage": {
                "name": "Leverage",
                "type": "int",
                "default": 10,
                "min": 1,
                "max": 125,
                "description": "Trading leverage",
                "group": "Position Sizing"
            },
            "tradesPerDay": {
                "name": "Trades Per Day",
                "type": "int",
                "default": 99,
                "min": 1,
                "max": 999,
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


# ═══════════════════════════════════════════════════════════════════════════════
#                               ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/admin/sessions")
async def list_sessions():
    """List all sessions (admin)"""
    manager = get_session_manager()

    sessions = []
    for user_id, session in manager._sessions.items():
        sessions.append(session.to_dict())

    return {
        "total": len(sessions),
        "active": manager.active_sessions,
        "sessions": sessions
    }


@app.get("/api/v1/admin/resources")
async def get_resources():
    """Get resource usage"""
    process = psutil.Process()

    return {
        "cpu_percent": process.cpu_percent(),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "threads": process.num_threads(),
        "uptime": int((datetime.utcnow() - START_TIME).total_seconds())
    }


@app.post("/api/v1/admin/close-positions/{user_id}")
async def emergency_close_positions(user_id: str):
    """Emergency close all positions for a user"""
    manager = get_session_manager()
    session = manager.get_session(user_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    if not session.robot or session.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Robot not running")

    try:
        await session.robot._close_all_positions()
        return {"message": "All positions closed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#                               DEBUG ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/debug/sessions")
async def debug_sessions():
    """Debug session info"""
    manager = get_session_manager()

    result = {}
    for user_id, session in manager._sessions.items():
        result[user_id] = {
            "status": session.status.value,
            "has_robot": session.robot is not None,
            "has_webhook": session.webhook_client is not None,
            "has_task": session.task is not None,
            "robot_state": session.robot.state.value if session.robot else None
        }

    return result
