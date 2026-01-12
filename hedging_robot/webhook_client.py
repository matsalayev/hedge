"""
Webhook Client - HEMA platformasiga trade eventlarini yuborish

Trade ochilganda, yopilganda, profit target bo'lganda HEMA ga webhook yuboriladi
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime

import aiohttp

logger = logging.getLogger(__name__)

# M10 fix - Webhook queue limit
MAX_QUEUE_SIZE = 1000


@dataclass
class WebhookConfig:
    """Webhook sozlamalari"""
    url: str
    secret: str
    timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0


class WebhookClient:
    """
    HEMA platformasiga webhook yuboruvchi client

    Hedging robot uchun maxsus eventlar
    """

    def __init__(self, config: WebhookConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)  # M10 fix
        self._worker_task: Optional[asyncio.Task] = None
        self._user_id: Optional[str] = None
        # G9 fix - Queue overflow metrics
        self._dropped_events: int = 0
        self._sent_events: int = 0
        self._failed_events: int = 0

    def set_user_id(self, user_id: str):
        """Set user ID for webhook events"""
        self._user_id = user_id

    async def start(self):
        """Webhook worker'ni ishga tushirish"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info(f"Webhook client started: {self.config.url}")

    async def stop(self):
        """Webhook worker'ni to'xtatish"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("Webhook client stopped")

    def _generate_signature(self, timestamp: str, payload: str) -> str:
        """HMAC-SHA256 signature yaratish"""
        message = f"{timestamp}.{payload}"
        return hmac.new(
            self.config.secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _send_event(
        self,
        event_type: str,
        user_bot_id: str,
        data: Dict[str, Any]
    ) -> bool:
        """Event yuborish"""
        event = {
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {
                "userId": self._user_id or "",
                "userBotId": user_bot_id,
                **data
            }
        }

        # M10 fix - Queue to'lgan bo'lsa, timeout bilan kutish
        # N6 fix - Timeout 0.5s -> 2s (yetarli vaqt berish)
        try:
            await asyncio.wait_for(
                self._queue.put(event),
                timeout=2.0
            )
            return True
        except asyncio.TimeoutError:
            # G9 fix - Dropped event metric
            self._dropped_events += 1
            logger.warning(
                f"Webhook queue full after 2s, dropping {event_type} event "
                f"(total dropped: {self._dropped_events})"
            )
            return False
        except asyncio.QueueFull:
            # G9 fix - Dropped event metric
            self._dropped_events += 1
            logger.warning(
                f"Webhook queue full, dropping {event_type} event "
                f"(total dropped: {self._dropped_events})"
            )
            return False

    async def send_trade_opened(
        self,
        user_bot_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        order_id: str,
        grid_level: int = 1
    ):
        """Grid order ochildi eventi"""
        await self._send_event(
            "trade_opened",
            user_bot_id,
            {
                "trade": {
                    "id": order_id,
                    "exchangeOrderId": order_id,
                    "pair": symbol,
                    "side": side.upper(),
                    "type": "MARKET",
                    "amount": quantity,
                    "price": price,
                    "cost": price * quantity,
                    "fee": 0,
                    "feeCurrency": "USDT",
                    "gridLevel": grid_level,
                    "openedAt": datetime.utcnow().isoformat() + "Z"
                }
            }
        )

    async def send_trade_closed(
        self,
        user_bot_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        pnl: float,
        reason: str = "MANUAL"
    ):
        """Trade yopildi eventi"""
        # HEMA 0-100 formatni kutadi (5 = 5%), 0.0-1.0 emas!
        pnl_percent = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        if side.upper() == "SELL":
            pnl_percent = -pnl_percent

        await self._send_event(
            "trade_closed",
            user_bot_id,
            {
                "trade": {
                    "id": f"close-{int(time.time()*1000)}",
                    "pair": symbol,
                    "side": side.upper(),
                    "type": "MARKET",
                    "amount": quantity,
                    "price": exit_price,
                    "cost": exit_price * quantity,
                    "fee": 0,
                    "feeCurrency": "USDT",
                    "pnl": pnl,
                    "pnlPercent": pnl_percent,
                    "closedAt": datetime.utcnow().isoformat() + "Z",
                    "reason": reason
                }
            }
        )

    async def send_positions_closed(
        self,
        user_bot_id: str,
        symbol: str,
        side: str,
        positions_count: int,
        total_pnl: float,
        avg_entry_price: float,
        exit_price: float,
        reason: str = "PROFIT_TARGET"
    ):
        """Barcha pozitsiyalar yopildi eventi (profit target)"""
        pnl_percent = 0.0
        if avg_entry_price > 0:
            # HEMA 0-100 formatni kutadi (5 = 5%), 0.0-1.0 emas!
            pnl_percent = (exit_price - avg_entry_price) / avg_entry_price * 100
            if side.upper() == "SELL":
                pnl_percent = -pnl_percent

        await self._send_event(
            "trade_closed",
            user_bot_id,
            {
                "trade": {
                    "id": f"profit-{int(time.time()*1000)}",
                    "pair": symbol,
                    "side": side.upper(),
                    "type": "PROFIT_TARGET",
                    "amount": positions_count,
                    "price": exit_price,
                    "entryPrice": avg_entry_price,
                    "cost": exit_price * positions_count,
                    "fee": 0,
                    "feeCurrency": "USDT",
                    "pnl": total_pnl,
                    "pnlPercent": round(pnl_percent, 4),
                    "closedAt": datetime.utcnow().isoformat() + "Z"
                },
                "reason": reason,
                "positionsClosed": positions_count
            }
        )

    async def send_global_limit_hit(
        self,
        user_bot_id: str,
        symbol: str,
        total_pnl: float,
        limit_type: str,  # "PROFIT" or "LOSS"
        limit_value: float
    ):
        """Global limit eventi"""
        await self._send_event(
            "global_limit_hit",
            user_bot_id,
            {
                "symbol": symbol,
                "totalPnl": total_pnl,
                "limitType": limit_type,
                "limitValue": limit_value,
                "message": f"Global {limit_type.lower()} limit reached: {total_pnl} USDT"
            }
        )

    async def send_status_changed(
        self,
        user_bot_id: str,
        status: str,
        message: str = ""
    ):
        """Status o'zgarishi eventi"""
        await self._send_event(
            "status_changed",
            user_bot_id,
            {
                "previousStatus": "",
                "newStatus": status.lower(),
                "reason": message
            }
        )

    async def send_error(
        self,
        user_bot_id: str,
        error_code: str,
        error_message: str
    ):
        """Xatolik eventi"""
        await self._send_event(
            "error_occurred",
            user_bot_id,
            {
                "error": {
                    "code": error_code,
                    "message": error_message,
                    "severity": "medium"
                }
            }
        )

    async def send_balance_warning(
        self,
        user_bot_id: str,
        current_balance: float,
        required_balance: float,
        message: str = ""
    ):
        """Balance ogohlantirishi"""
        await self._send_event(
            "balance_warning",
            user_bot_id,
            {
                "currentBalance": current_balance,
                "requiredBalance": required_balance,
                "message": message or f"Balance is low: ${current_balance}"
            }
        )

    async def send_status_update(
        self,
        user_bot_id: str,
        symbol: str,
        current_price: float,
        sma_value: float,
        sar_value: float,
        cci_value: float,
        signal: str,  # "BUY", "SELL", "NONE"
        balance: float,
        buy_positions: List[Dict],
        sell_positions: List[Dict],
        stats: Dict,
        settings: Dict,
        runtime: Dict = None
    ):
        """
        Real-time status update - Hedging robot uchun

        Har bir tick da yuboriladi
        """
        # Har bir pozitsiya uchun PnL hisoblash
        # USDT-M Perpetual Futures: PnL = lot * price_change (leverage ta'sir qilmaydi!)
        def calc_position_pnl(pos, side):
            entry = pos.get("entry_price", 0)
            lot = pos.get("lot", 0)
            # G1 fix - barcha qiymatlarni tekshirish (division by zero oldini olish)
            if entry <= 0 or lot <= 0 or current_price <= 0:
                return 0.0, 0.0
            if side == "buy":
                # PnL = lot * (current - entry) - leverage kerak emas!
                pnl = (current_price - entry) * lot
                # HEMA 0-100 formatni kutadi (5 = 5%), 0.0-1.0 emas!
                pnl_percent = (current_price - entry) / entry * 100
            else:
                # PnL = lot * (entry - current) - leverage kerak emas!
                pnl = (entry - current_price) * lot
                # HEMA 0-100 formatni kutadi (5 = 5%), 0.0-1.0 emas!
                pnl_percent = (entry - current_price) / entry * 100
            return round(pnl, 4), round(pnl_percent, 6)

        # BUY pozitsiyalarni tayyorlash
        buy_with_pnl = []
        for p in buy_positions:
            pnl, pnl_pct = calc_position_pnl(p, "buy")
            buy_with_pnl.append({
                "price": p.get("entry_price", 0),
                "lot": p.get("lot", 0),
                "orderId": p.get("id", ""),
                "gridLevel": p.get("grid_level", 1),
                "pnl": pnl,
                "pnlPercent": pnl_pct,
                "openedAt": p.get("opened_at", "")
            })

        # SELL pozitsiyalarni tayyorlash
        sell_with_pnl = []
        for p in sell_positions:
            pnl, pnl_pct = calc_position_pnl(p, "sell")
            sell_with_pnl.append({
                "price": p.get("entry_price", 0),
                "lot": p.get("lot", 0),
                "orderId": p.get("id", ""),
                "gridLevel": p.get("grid_level", 1),
                "pnl": pnl,
                "pnlPercent": pnl_pct,
                "openedAt": p.get("opened_at", "")
            })

        # Jami PnL
        total_buy_pnl = sum(p["pnl"] for p in buy_with_pnl)
        total_sell_pnl = sum(p["pnl"] for p in sell_with_pnl)

        await self._send_event(
            "status_update",
            user_bot_id,
            {
                "symbol": symbol,
                "currentPrice": current_price,
                "indicators": {
                    "sma": round(sma_value, 2),
                    "sar": round(sar_value, 2),
                    "cci": round(cci_value, 2),
                    "signal": signal
                },
                "balance": round(balance, 2),
                "positions": {
                    "buy": buy_with_pnl,
                    "sell": sell_with_pnl,
                    "buyCount": len(buy_with_pnl),
                    "sellCount": len(sell_with_pnl),
                    "buyPnl": round(total_buy_pnl, 4),
                    "sellPnl": round(total_sell_pnl, 4),
                    "totalPnl": round(total_buy_pnl + total_sell_pnl, 4)
                },
                "grid": {
                    "multiplier": settings.get("multiplier", 1.5),
                    "spacePercent": settings.get("space_percent", 0.5),
                    "maxBuyOrders": settings.get("max_buy_orders", 5),
                    "maxSellOrders": settings.get("max_sell_orders", 5)
                },
                "profit": {
                    "singleOrderProfit": settings.get("single_order_profit", 3.0),
                    "pairGlobalProfit": settings.get("pair_global_profit", 1.0),
                    "globalProfit": settings.get("global_profit", 0),
                    "maxLoss": settings.get("max_loss", 0)
                },
                "performance": {
                    "totalTrades": stats.get("total_trades", 0),
                    "winningTrades": stats.get("winning_trades", 0),
                    "losingTrades": stats.get("losing_trades", 0),
                    "winRate": stats.get("win_rate", 0),
                    "totalPnL": round(stats.get("total_profit", 0), 4),
                    "unrealizedPnL": round(total_buy_pnl + total_sell_pnl, 4)
                },
                "settings": {
                    "leverage": settings.get("leverage", 10),
                    "timeframe": settings.get("timeframe", "1H"),
                    "baseLot": settings.get("base_lot", 0.01),
                    "useSmaEntry": settings.get("use_sma_sar", True),
                    "cciPeriod": settings.get("cci_period", 0)
                },
                "runtime": runtime or {
                    "tick": stats.get("tick", 0),
                    "uptime": 0,
                    "startedAt": "",
                    "lastTradeAt": ""
                }
            }
        )

    async def _process_queue(self):
        """Queue'dan eventlarni yuborish"""
        while True:
            try:
                event = await self._queue.get()
                await self._send_with_retry(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Webhook queue error: {e}")

    async def _send_with_retry(self, event: Dict[str, Any]) -> bool:
        """Retry bilan webhook yuborish"""
        payload = json.dumps(event)
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, payload)
        webhook_id = f"{event['data']['userBotId']}-{timestamp}-{uuid.uuid4().hex[:8]}"

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Secret": self.config.secret,
            "X-Webhook-ID": webhook_id,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": signature
        }

        logger.debug(f"[WEBHOOK] Sending: {event['event']}")

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    self.config.url,
                    data=payload,
                    headers=headers
                ) as response:
                    response_text = await response.text()

                    if response.status in (200, 201, 202):
                        # G9 fix - Sent event metric
                        self._sent_events += 1
                        logger.debug(f"[WEBHOOK] SUCCESS: {event['event']}")
                        return True
                    else:
                        logger.warning(
                            f"[WEBHOOK] FAILED (attempt {attempt + 1}): "
                            f"status={response.status}, body={response_text[:200]}"
                        )

            except asyncio.TimeoutError:
                logger.warning(f"[WEBHOOK] TIMEOUT (attempt {attempt + 1})")
            except aiohttp.ClientError as e:
                logger.warning(f"[WEBHOOK] CONNECTION ERROR (attempt {attempt + 1}): {e}")

            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        # G9 fix - Failed event metric
        self._failed_events += 1
        logger.error(f"Webhook failed after {self.config.max_retries} attempts: {event['event']}")
        return False

    def get_stats(self) -> Dict[str, Any]:
        """
        G9 fix - Webhook statistikasini olish

        Returns:
            Dict with webhook stats
        """
        return {
            "queue_size": self._queue.qsize(),
            "queue_max": MAX_QUEUE_SIZE,
            "sent_events": self._sent_events,
            "dropped_events": self._dropped_events,
            "failed_events": self._failed_events,
            "total_events": self._sent_events + self._dropped_events + self._failed_events
        }
