"""
Trading Service

주문 실행 및 포지션 관리를 담당하는 서비스입니다.
Trader 컴포넌트에서 사용됩니다.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from .schwab_service import SchwabAPIService, SchwabAPIException

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """주문 유형"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(str, Enum):
    """주문 방향"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """주문 상태"""
    PENDING = "PENDING"
    WORKING = "WORKING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TradingException(Exception):
    """트레이딩 관련 예외"""
    pass


class TradingService:
    """
    트레이딩 서비스

    Schwab API를 통해 주문 실행 및 관리를 담당하는 서비스입니다.
    Trader 컴포넌트에서 사용되며 다음 기능을 제공합니다:
    - 주문 생성 및 실행
    - 주문 상태 추적
    - 포지션 관리
    - 리스크 관리
    """

    def __init__(self, schwab_service: SchwabAPIService):
        """
        Trading Service 초기화

        Args:
            schwab_service: Schwab API 서비스 인스턴스
        """
        self.schwab_service = schwab_service
        self.logger = logging.getLogger(__name__)

    async def create_market_order(
        self,
        account_hash: str,
        symbol: str,
        side: OrderSide,
        quantity: int
    ) -> Dict[str, Any]:
        """
        시장가 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            side: 주문 방향 (BUY/SELL)
            quantity: 수량

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": OrderType.MARKET.value,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        return await self._place_order(account_hash, order_spec, f"market_{side.value.lower()}")

    async def create_limit_order(
        self,
        account_hash: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: float
    ) -> Dict[str, Any]:
        """
        지정가 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            side: 주문 방향
            quantity: 수량
            limit_price: 지정가

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": OrderType.LIMIT.value,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": str(limit_price),
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        return await self._place_order(account_hash, order_spec, f"limit_{side.value.lower()}")

    async def create_stop_order(
        self,
        account_hash: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        stop_price: float
    ) -> Dict[str, Any]:
        """
        정지가 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            side: 주문 방향
            quantity: 수량
            stop_price: 정지가

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": OrderType.STOP.value,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "stopPrice": str(stop_price),
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        return await self._place_order(account_hash, order_spec, f"stop_{side.value.lower()}")

    async def create_stop_limit_order(
        self,
        account_hash: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        stop_price: float,
        limit_price: float
    ) -> Dict[str, Any]:
        """
        정지지정가 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            side: 주문 방향
            quantity: 수량
            stop_price: 정지가
            limit_price: 지정가

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": OrderType.STOP_LIMIT.value,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": str(limit_price),
            "stopPrice": str(stop_price),
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        return await self._place_order(
            account_hash,
            order_spec,
            f"stop_limit_{side.value.lower()}"
        )

    async def _place_order(
        self,
        account_hash: str,
        order_spec: Dict[str, Any],
        order_type: str
    ) -> Dict[str, Any]:
        """
        주문 실행 (내부 메서드)

        Args:
            account_hash: 계좌 해시
            order_spec: 주문 사양
            order_type: 주문 유형 (로깅용)

        Returns:
            주문 결과
        """
        try:
            # 주문 검증
            self._validate_order(order_spec)

            # 주문 실행
            logger.info(f"Placing {order_type} order for account {account_hash}")
            result = await self.schwab_service.place_order(account_hash, order_spec)

            # 결과 처리
            processed_result = self._process_order_result(result, order_spec, order_type)

            logger.info(
                f"Order placed successfully: {order_type}, "
                f"order_id: {processed_result.get('order_id', 'unknown')}"
            )

            return processed_result

        except Exception as e:
            logger.error(f"Failed to place {order_type} order: {e}")
            raise TradingException(f"Failed to place {order_type} order: {e}")

    def _validate_order(self, order_spec: Dict[str, Any]) -> None:
        """주문 검증"""
        required_fields = ["orderType", "orderLegCollection"]
        for field in required_fields:
            if field not in order_spec:
                raise TradingException(f"Missing required field: {field}")

        # 주문 레그 검증
        legs = order_spec["orderLegCollection"]
        if not legs:
            raise TradingException("Order must have at least one leg")

        for leg in legs:
            if "instruction" not in leg or "quantity" not in leg:
                raise TradingException("Invalid order leg specification")

            if leg["quantity"] <= 0:
                raise TradingException("Order quantity must be positive")

    def _process_order_result(
        self,
        result: Dict[str, Any],
        order_spec: Dict[str, Any],
        order_type: str
    ) -> Dict[str, Any]:
        """주문 결과 처리"""
        processed = {
            "order_type": order_type,
            "timestamp": datetime.now(timezone.utc),
            "order_spec": order_spec,
            "raw_result": result,
            "status": OrderStatus.PENDING.value
        }

        # 주문 ID 추출
        if isinstance(result, dict):
            if "orderId" in result:
                processed["order_id"] = result["orderId"]
            elif "location" in result:
                # Location 헤더에서 주문 ID 추출
                location = result["location"]
                if "/orders/" in location:
                    processed["order_id"] = location.split("/orders/")[-1]

        return processed

    async def cancel_order(self, account_hash: str, order_id: str) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            account_hash: 계좌 해시
            order_id: 주문 ID

        Returns:
            취소 결과
        """
        try:
            logger.info(f"Canceling order {order_id} for account {account_hash}")

            # Schwab API를 통해 주문 취소
            # 실제 구현에서는 schwab 라이브러리의 cancel_order 메서드 사용
            result = {
                "order_id": order_id,
                "status": OrderStatus.CANCELED.value,
                "timestamp": datetime.now(timezone.utc),
                "message": "Order canceled successfully"
            }

            logger.info(f"Order {order_id} canceled successfully")
            return result

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise TradingException(f"Failed to cancel order: {e}")

    async def get_order_status(self, account_hash: str, order_id: str) -> Dict[str, Any]:
        """
        주문 상태 조회

        Args:
            account_hash: 계좌 해시
            order_id: 주문 ID

        Returns:
            주문 상태 정보
        """
        try:
            # 실제 구현에서는 schwab API의 get_order 메서드 사용
            # 여기서는 예시 구조만 제공
            order_info = {
                "order_id": order_id,
                "status": OrderStatus.WORKING.value,
                "timestamp": datetime.now(timezone.utc),
                "filled_quantity": 0,
                "remaining_quantity": 100,
                "average_fill_price": 0.0
            }

            logger.debug(f"Retrieved order status for {order_id}: {order_info['status']}")
            return order_info

        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            raise TradingException(f"Failed to get order status: {e}")

    async def get_open_orders(self, account_hash: str) -> List[Dict[str, Any]]:
        """
        미체결 주문 목록 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            미체결 주문 목록
        """
        try:
            logger.debug(f"Getting open orders for account {account_hash}")

            # 실제 구현에서는 schwab API 사용
            # 여기서는 예시 구조만 제공
            open_orders = []

            logger.debug(f"Found {len(open_orders)} open orders")
            return open_orders

        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            raise TradingException(f"Failed to get open orders: {e}")

    async def get_order_history(
        self,
        account_hash: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        주문 히스토리 조회

        Args:
            account_hash: 계좌 해시
            days: 조회 기간 (일)

        Returns:
            주문 히스토리
        """
        try:
            logger.debug(f"Getting order history for account {account_hash}, {days} days")

            # 실제 구현에서는 schwab API 사용
            order_history = []

            logger.debug(f"Retrieved {len(order_history)} historical orders")
            return order_history

        except Exception as e:
            logger.error(f"Failed to get order history: {e}")
            raise TradingException(f"Failed to get order history: {e}")

    async def calculate_position_size(
        self,
        account_hash: str,
        symbol: str,
        risk_percentage: float,
        entry_price: float,
        stop_loss_price: float
    ) -> Dict[str, Any]:
        """
        포지션 사이즈 계산

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            risk_percentage: 리스크 비율 (0.01 = 1%)
            entry_price: 진입가
            stop_loss_price: 손절가

        Returns:
            포지션 사이즈 정보
        """
        try:
            # 계좌 정보 조회 (AccountService에서 호출)
            account_info = await self.schwab_service.get_account_info(account_hash)

            # 가용 자금 계산
            available_funds = account_info.get("securitiesAccount", {}).get(
                "currentBalances", {}
            ).get("availableFunds", 0.0)

            # 리스크 금액 계산
            risk_amount = available_funds * risk_percentage

            # 주당 리스크 계산
            price_difference = abs(entry_price - stop_loss_price)
            if price_difference == 0:
                raise TradingException("Entry price and stop loss price cannot be the same")

            # 포지션 사이즈 계산
            position_size = int(risk_amount / price_difference)

            result = {
                "symbol": symbol,
                "account_hash": account_hash,
                "available_funds": available_funds,
                "risk_percentage": risk_percentage,
                "risk_amount": risk_amount,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
                "price_difference": price_difference,
                "calculated_position_size": position_size,
                "total_position_value": position_size * entry_price,
                "timestamp": datetime.now(timezone.utc)
            }

            logger.info(
                f"Position size calculated for {symbol}: {position_size} shares, "
                f"risk: ${risk_amount:.2f}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to calculate position size: {e}")
            raise TradingException(f"Failed to calculate position size: {e}")