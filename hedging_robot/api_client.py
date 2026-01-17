"""
Hedging Grid Robot - Bitget API Client

REST API va order management
"""

import hmac
import hashlib
import base64
import time
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp

from .config import APIConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                               EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class BitgetAPIError(Exception):
    """Bitget API xatosi"""
    def __init__(self, code: str, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


class BitgetAuthError(BitgetAPIError):
    """Autentifikatsiya xatosi"""
    pass


class BitgetRateLimitError(BitgetAPIError):
    """Rate limit xatosi"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#                               DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    """Pozitsiya ma'lumotlari"""
    symbol: str
    side: str  # 'long' or 'short'
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    liquidation_price: float
    leverage: int
    margin_mode: str


@dataclass
class Order:
    """Order ma'lumotlari"""
    order_id: str
    symbol: str
    side: str
    size: float
    price: float
    order_type: str
    status: str
    filled_size: float
    avg_fill_price: float
    create_time: int


# ═══════════════════════════════════════════════════════════════════════════════
#                               BITGET CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class BitgetClient:
    """
    Bitget Futures API Client

    REST API orqali trading operatsiyalari
    """

    def __init__(self, config: APIConfig):
        """
        Args:
            config: API konfiguratsiyasi
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    # ─────────────────────────────────────────────────────────────────────────
    #                           SESSION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP session olish"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Sessionni yopish"""
        if self._session and not self._session.closed:
            await self._session.close()

    # ─────────────────────────────────────────────────────────────────────────
    #                           AUTHENTICATION
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_signature(self, timestamp: str, method: str,
                            path: str, body: str = "") -> str:
        """
        HMAC-SHA256 imzo yaratish

        Bitget imzo formati:
        sign = base64(hmac_sha256(secret, timestamp + method + path + body))
        """
        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.config.SECRET_KEY.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(signature.digest()).decode('utf-8')

    def _get_headers(self, method: str, path: str, body: str = "") -> Dict:
        """API headers yaratish"""
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_signature(timestamp, method, path, body)

        headers = {
            "ACCESS-KEY": self.config.API_KEY,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.config.PASSPHRASE,
            "Content-Type": "application/json",
            "locale": "en-US"
        }

        # Demo mode uchun maxsus header
        if self.config.DEMO_MODE:
            headers["paptrading"] = "1"

        return headers

    # ─────────────────────────────────────────────────────────────────────────
    #                           REQUEST METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str,
                       params: Optional[Dict] = None,
                       body: Optional[Dict] = None) -> Dict:
        """
        API so'rov yuborish

        Args:
            method: HTTP method (GET, POST, DELETE)
            path: API endpoint
            params: Query parameters
            body: Request body

        Returns:
            API javobi
        """
        session = await self._get_session()

        url = self.config.BASE_URL + path
        request_path = path

        # Query string qo'shish (SORTED - imzo uchun muhim!)
        if params:
            query = urlencode(sorted(params.items()))
            request_path = f"{path}?{query}"
            url = f"{url}?{query}"

        # Body
        body_str = json.dumps(body) if body else ""

        # Headers (request_path ishlatiladi, path emas)
        headers = self._get_headers(method, request_path, body_str)

        # Request
        for attempt in range(self.config.MAX_RETRIES):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=body_str if body else None
                ) as response:

                    text = await response.text()

                    # Rate limit
                    if response.status == 429:
                        wait_time = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limit! {wait_time}s kutilmoqda...")
                        await asyncio.sleep(wait_time)
                        continue

                    # Parse response
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        raise BitgetAPIError("PARSE_ERROR", f"JSON parse error: {text}")

                    # Error check
                    if data.get("code") != "00000":
                        code = data.get("code", "UNKNOWN")
                        msg = data.get("msg", "Unknown error")

                        if "signature" in msg.lower() or "auth" in msg.lower():
                            raise BitgetAuthError(code, msg)
                        if "rate" in msg.lower() or "limit" in msg.lower():
                            raise BitgetRateLimitError(code, msg)

                        # N4 fix - Temporary errors uchun retry
                        # 50000: System busy, please try again later
                        # 40034: Request too frequent
                        if code in ("50000", "40034", "40001"):
                            logger.warning(f"Temporary error (attempt {attempt + 1}): [{code}] {msg}")
                            if attempt < self.config.MAX_RETRIES - 1:
                                await asyncio.sleep(2 ** attempt)
                                # Headers yangilash (timestamp eskiradi)
                                headers = self._get_headers(method, request_path, body_str)
                                continue
                            # Oxirgi urinishda xatoni tashlash

                        raise BitgetAPIError(code, msg, data)

                    return data.get("data", data)

            except asyncio.TimeoutError:
                # G3 fix - Timeout xatosini handle qilish
                logger.warning(f"Request timeout (attempt {attempt + 1}): {url}")
                if attempt < self.config.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    # Headers yangilash (timestamp eskiradi)
                    headers = self._get_headers(method, request_path, body_str)
                else:
                    raise BitgetAPIError("TIMEOUT", f"Request timeout after {self.config.TIMEOUT}s")

            except aiohttp.ClientError as e:
                logger.error(f"Request error (attempt {attempt + 1}): {e}")
                if attempt < self.config.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise BitgetAPIError("NETWORK_ERROR", str(e))

        raise BitgetAPIError("MAX_RETRIES", "Maksimal urinishlar soni oshdi")

    async def get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """GET so'rov"""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, body: Optional[Dict] = None) -> Dict:
        """POST so'rov"""
        return await self._request("POST", path, body=body)

    async def delete(self, path: str, body: Optional[Dict] = None) -> Dict:
        """DELETE so'rov"""
        return await self._request("DELETE", path, body=body)

    # ─────────────────────────────────────────────────────────────────────────
    #                           ACCOUNT METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_account(self, product_type: str = "USDT-FUTURES") -> Dict:
        """Hisob ma'lumotlarini olish"""
        params = {"productType": product_type}
        return await self.get("/api/v2/mix/account/accounts", params)

    async def get_balance(self, product_type: str = "USDT-FUTURES",
                          margin_coin: str = "USDT") -> float:
        """Balansni olish"""
        data = await self.get_account(product_type)
        if isinstance(data, list):
            for account in data:
                if account.get("marginCoin") == margin_coin:
                    return float(account.get("available", 0))
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int,
                          product_type: str = "USDT-FUTURES",
                          margin_coin: str = "USDT") -> Dict:
        """Leverage o'rnatish"""
        body = {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": margin_coin,
            "leverage": str(leverage)
        }
        return await self.post("/api/v2/mix/account/set-leverage", body)

    # ─────────────────────────────────────────────────────────────────────────
    #                           MARKET DATA
    # ─────────────────────────────────────────────────────────────────────────

    async def get_ticker(self, symbol: str,
                         product_type: str = "USDT-FUTURES") -> Dict:
        """Ticker (narx) olish"""
        params = {"symbol": symbol, "productType": product_type}
        data = await self.get("/api/v2/mix/market/ticker", params)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data

    async def get_price(self, symbol: str,
                        product_type: str = "USDT-FUTURES") -> float:
        """Joriy narxni olish"""
        ticker = await self.get_ticker(symbol, product_type)
        return float(ticker.get("lastPr", ticker.get("last", 0)))

    async def get_candles(self, symbol: str, granularity: str = "1H",
                          limit: int = 100,
                          product_type: str = "USDT-FUTURES") -> List[Dict]:
        """
        Candlestick ma'lumotlarini olish

        Args:
            symbol: Trading pair
            granularity: Timeframe (1m, 5m, 15m, 30m, 1H, 4H, 1D)
            limit: Candlelar soni
            product_type: Product type

        Returns:
            Candle ro'yxati
        """
        params = {
            "symbol": symbol,
            "productType": product_type,
            "granularity": granularity,
            "limit": str(limit)
        }
        return await self.get("/api/v2/mix/market/candles", params)

    # ─────────────────────────────────────────────────────────────────────────
    #                           POSITION METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_positions(self, symbol: str = None,
                            product_type: str = "USDT-FUTURES",
                            margin_coin: str = "USDT") -> List[Position]:
        """Pozitsiyalarni olish"""
        params = {"productType": product_type, "marginCoin": margin_coin}
        if symbol:
            params["symbol"] = symbol

        data = await self.get("/api/v2/mix/position/all-position", params)

        positions = []
        if data:
            for item in data:
                if float(item.get("total", 0)) > 0:
                    positions.append(Position(
                        symbol=item.get("symbol", ""),
                        side=item.get("holdSide", ""),
                        size=float(item.get("total", 0)),
                        entry_price=float(item.get("openPriceAvg", 0)),
                        mark_price=float(item.get("markPrice", 0)),
                        unrealized_pnl=float(item.get("unrealizedPL", 0)),
                        liquidation_price=float(item.get("liquidationPrice", 0)),
                        leverage=int(item.get("leverage", 1)),
                        margin_mode=item.get("marginMode", "")
                    ))

        return positions

    async def get_position(self, symbol: str, side: str,
                           product_type: str = "USDT-FUTURES") -> Optional[Position]:
        """Bitta pozitsiyani olish"""
        positions = await self.get_positions(symbol, product_type)
        for pos in positions:
            if pos.side == side:
                return pos
        return None

    # ─────────────────────────────────────────────────────────────────────────
    #                           ORDER METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def place_order(self, symbol: str, side: str, trade_side: str,
                          size: float, order_type: str = "market",
                          price: Optional[float] = None,
                          product_type: str = "USDT-FUTURES",
                          margin_coin: str = "USDT",
                          tp_price: Optional[float] = None,
                          sl_price: Optional[float] = None) -> Dict:
        """
        Order yaratish

        Args:
            symbol: Trading pair
            side: 'buy' yoki 'sell'
            trade_side: 'open' (ochish) yoki 'close' (yopish)
            size: Hajm
            order_type: 'market' yoki 'limit'
            price: Limit order uchun narx
            product_type: Product type
            margin_coin: Margin valyutasi
            tp_price: Take Profit narx
            sl_price: Stop Loss narx

        Returns:
            Order javobi
        """
        body = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": "crossed",
            "marginCoin": margin_coin,
            "side": side,
            "tradeSide": trade_side,
            "orderType": order_type,
            "size": str(size),
            "force": "GTC"
        }

        if order_type == "limit" and price:
            body["price"] = str(price)

        # TP/SL
        if tp_price:
            body["presetStopSurplusPrice"] = str(tp_price)
        if sl_price:
            body["presetStopLossPrice"] = str(sl_price)

        return await self.post("/api/v2/mix/order/place-order", body)

    async def cancel_order(self, symbol: str, order_id: str,
                           product_type: str = "USDT-FUTURES") -> Dict:
        """Order bekor qilish"""
        body = {
            "symbol": symbol,
            "productType": product_type,
            "orderId": order_id
        }
        return await self.post("/api/v2/mix/order/cancel-order", body)

    async def get_open_orders(self, symbol: str = None,
                              product_type: str = "USDT-FUTURES") -> List[Dict]:
        """Ochiq orderlarni olish"""
        params = {"productType": product_type}
        if symbol:
            params["symbol"] = symbol

        return await self.get("/api/v2/mix/order/orders-pending", params)

    async def cancel_all_orders(self, symbol: str,
                                product_type: str = "USDT-FUTURES") -> Dict:
        """Barcha orderlarni bekor qilish"""
        body = {
            "symbol": symbol,
            "productType": product_type
        }
        return await self.post("/api/v2/mix/order/cancel-all-orders", body)

    # ─────────────────────────────────────────────────────────────────────────
    #                           SHORTCUT METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def open_long(self, symbol: str, size: float,
                        tp_price: Optional[float] = None,
                        sl_price: Optional[float] = None) -> Dict:
        """LONG pozitsiya ochish (market order)"""
        return await self.place_order(
            symbol=symbol,
            side="buy",
            trade_side="open",
            size=size,
            order_type="market",
            tp_price=tp_price,
            sl_price=sl_price
        )

    async def open_short(self, symbol: str, size: float,
                         tp_price: Optional[float] = None,
                         sl_price: Optional[float] = None) -> Dict:
        """SHORT pozitsiya ochish (market order)"""
        return await self.place_order(
            symbol=symbol,
            side="sell",
            trade_side="open",
            size=size,
            order_type="market",
            tp_price=tp_price,
            sl_price=sl_price
        )

    async def close_long(self, symbol: str, size: float) -> Dict:
        """LONG pozitsiyani yopish"""
        return await self.place_order(
            symbol=symbol,
            side="sell",
            trade_side="close",
            size=size,
            order_type="market"
        )

    async def close_short(self, symbol: str, size: float) -> Dict:
        """SHORT pozitsiyani yopish"""
        return await self.place_order(
            symbol=symbol,
            side="buy",
            trade_side="close",
            size=size,
            order_type="market"
        )

    async def close_all_positions(self, symbol: str,
                                  product_type: str = "USDT-FUTURES") -> Dict:
        """Barcha pozitsiyalarni yopish"""
        body = {
            "symbol": symbol,
            "productType": product_type
        }
        return await self.post("/api/v2/mix/order/close-positions", body)

    # ─────────────────────────────────────────────────────────────────────────
    #                           TP/SL METHODS
    # ─────────────────────────────────────────────────────────────────────────

    async def modify_tpsl(self, symbol: str, side: str,
                          tp_price: Optional[float] = None,
                          sl_price: Optional[float] = None,
                          product_type: str = "USDT-FUTURES") -> Dict:
        """
        Pozitsiya TP/SL ni o'zgartirish

        ESLATMA: Bu endpoint Bitget API v2 da mavjud emas (40404 xato).
        TP/SL local monitoring orqali amalga oshiriladi.
        To'g'ri endpoint: /api/v2/mix/order/place-pos-tpsl (boshqa parametrlar bilan)

        Args:
            symbol: Trading pair
            side: 'long' yoki 'short'
            tp_price: Yangi Take Profit narx
            sl_price: Yangi Stop Loss narx
        """
        # TODO: Bitget API v2 da to'g'ri endpoint /api/v2/mix/order/place-pos-tpsl
        # Hozircha local TP/SL monitoring ishlatiladi, shuning uchun bu metod skip qilinadi
        logger.debug(f"modify_tpsl: Local TP/SL monitoring ishlatiladi (exchange-level TP/SL vaqtincha o'chirilgan)")
        return {"success": True, "note": "Local TP/SL monitoring used"}
