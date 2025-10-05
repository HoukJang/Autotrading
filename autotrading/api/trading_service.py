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
    CREDIT = "CREDIT"  # 옵션용 크레딧 주문
    DEBIT = "DEBIT"    # 옵션용 데빗 주문
    SELL_SHORT = "SELL_SHORT"  # 공매도
    SELL_SHORT_EXEMPT = "SELL_SHORT_EXEMPT"  # 공매도 예외
    WASH_SALE = "WASH_SALE"  # 워시세일


class OrderSide(str, Enum):
    """주문 방향"""
    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"  # 공매도
    BUY_TO_COVER = "BUY_TO_COVER"  # 공매도 포지션 정리

    # 옵션 전용 주문 방향
    BUY_TO_OPEN = "BUY_TO_OPEN"    # 옵션 매수 오픈
    BUY_TO_CLOSE = "BUY_TO_CLOSE"  # 옵션 매수 클로즈
    SELL_TO_OPEN = "SELL_TO_OPEN"  # 옵션 매도 오픈
    SELL_TO_CLOSE = "SELL_TO_CLOSE"  # 옵션 매도 클로즈


class OrderStatus(str, Enum):
    """주문 상태"""
    PENDING = "PENDING"
    WORKING = "WORKING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 부분 체결
    ACCEPTED = "ACCEPTED"  # 접수됨
    AWAITING_PARENT_ORDER = "AWAITING_PARENT_ORDER"  # 상위 주문 대기
    AWAITING_CONDITION = "AWAITING_CONDITION"  # 조건 대기
    AWAITING_MANUAL_REVIEW = "AWAITING_MANUAL_REVIEW"  # 수동 검토 대기
    AWAITING_OPEN = "AWAITING_OPEN"  # 시장 오픈 대기
    AWAITING_RELEASE_TIME = "AWAITING_RELEASE_TIME"  # 시간 대기


class StopType(str, Enum):
    """정지가 유형"""
    STANDARD = "STANDARD"      # 일반 정지가
    TRAILING_STOP = "TRAILING_STOP"  # 트레일링 스탑


class OrderStrategyType(str, Enum):
    """주문 전략 유형"""
    SINGLE = "SINGLE"    # 단일 주문
    OCO = "OCO"          # One Cancels Other
    TRIGGER = "TRIGGER"  # One Triggers Other


class ComplexOrderStrategyType(str, Enum):
    """복합 주문 전략 유형"""
    NONE = "NONE"
    COVERED = "COVERED"
    VERTICAL = "VERTICAL"
    BACK_RATIO = "BACK_RATIO"
    CALENDAR = "CALENDAR"
    DIAGONAL = "DIAGONAL"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    COLLAR_SYNTHETIC = "COLLAR_SYNTHETIC"
    BUTTERFLY = "BUTTERFLY"
    CONDOR = "CONDOR"
    IRON_CONDOR = "IRON_CONDOR"
    VERTICAL_ROLL = "VERTICAL_ROLL"
    COLLAR_WITH_STOCK = "COLLAR_WITH_STOCK"
    DOUBLE_DIAGONAL = "DOUBLE_DIAGONAL"
    UNBALANCED_BUTTERFLY = "UNBALANCED_BUTTERFLY"
    UNBALANCED_CONDOR = "UNBALANCED_CONDOR"
    UNBALANCED_IRON_CONDOR = "UNBALANCED_IRON_CONDOR"
    UNBALANCED_VERTICAL_ROLL = "UNBALANCED_VERTICAL_ROLL"
    CUSTOM = "CUSTOM"


class Duration(str, Enum):
    """주문 지속 기간"""
    DAY = "DAY"  # 당일
    GOOD_TILL_CANCEL = "GOOD_TILL_CANCEL"  # 취소시까지 유효
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"  # 즉시 체결 또는 취소
    FILL_OR_KILL = "FILL_OR_KILL"  # 전량 체결 또는 취소


class Session(str, Enum):
    """거래 세션"""
    NORMAL = "NORMAL"        # 정규 거래시간
    ELECTRONIC = "ELECTRONIC"  # 전자 거래
    EXTENDED = "EXTENDED"    # 연장 거래시간
    SEAMLESS = "SEAMLESS"    # 심리스 거래


class SpecialInstruction(str, Enum):
    """특별 지시사항"""
    ALL_OR_NONE = "ALL_OR_NONE"  # 전량 체결 또는 미체결
    DO_NOT_REDUCE = "DO_NOT_REDUCE"  # 배당 조정 안함
    ALL_OR_NONE_SEC = "ALL_OR_NONE_SEC"  # 2차 시장 전량 체결


class AssetType(str, Enum):
    """자산 유형"""
    EQUITY = "EQUITY"      # 주식
    OPTION = "OPTION"      # 옵션
    INDEX = "INDEX"        # 지수
    MUTUAL_FUND = "MUTUAL_FUND"  # 뮤추얼 펀드
    CASH_EQUIVALENT = "CASH_EQUIVALENT"  # 현금성 자산
    FIXED_INCOME = "FIXED_INCOME"  # 채권
    CURRENCY = "CURRENCY"  # 통화


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

    async def create_trailing_stop_order(
        self,
        account_hash: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trail_offset: float,
        trail_type: str = "DOLLAR",
        duration: Duration = Duration.GOOD_TILL_CANCEL,
        session: Session = Session.NORMAL
    ) -> Dict[str, Any]:
        """
        트레일링 스탑 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            side: 주문 방향 (주로 SELL for 손절매)
            quantity: 수량
            trail_offset: 트레일링 오프셋 (달러 또는 퍼센트)
            trail_type: 트레일링 유형 ("DOLLAR" 또는 "PERCENT")
            duration: 주문 지속 기간
            session: 거래 세션

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": OrderType.STOP.value,
            "stopType": StopType.TRAILING_STOP.value,
            "session": session.value,
            "duration": duration.value,
            "orderStrategyType": OrderStrategyType.SINGLE.value,
            "stopPriceOffset": str(trail_offset),
            "orderLegCollection": [
                {
                    "instruction": side.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": AssetType.EQUITY.value
                    }
                }
            ]
        }

        # 퍼센트 트레일링인 경우 추가 설정
        if trail_type.upper() == "PERCENT":
            order_spec["stopPriceLinkBasis"] = "PERCENT"
        else:
            order_spec["stopPriceLinkBasis"] = "DOLLAR"

        return await self._place_order(
            account_hash,
            order_spec,
            f"trailing_stop_{side.value.lower()}_{trail_type.lower()}"
        )

    async def create_short_sell_order(
        self,
        account_hash: str,
        symbol: str,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        공매도 주문 생성

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            quantity: 수량
            order_type: 주문 유형 (MARKET 또는 LIMIT)
            limit_price: 지정가 (LIMIT 주문인 경우)

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": order_type.value,
            "session": Session.NORMAL.value,
            "duration": Duration.DAY.value,
            "orderStrategyType": OrderStrategyType.SINGLE.value,
            "orderLegCollection": [
                {
                    "instruction": OrderSide.SELL_SHORT.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": AssetType.EQUITY.value
                    }
                }
            ]
        }

        if order_type == OrderType.LIMIT and limit_price is not None:
            order_spec["price"] = str(limit_price)

        return await self._place_order(
            account_hash,
            order_spec,
            f"short_sell_{order_type.value.lower()}"
        )

    async def create_buy_to_cover_order(
        self,
        account_hash: str,
        symbol: str,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        공매도 포지션 정리 주문 생성 (Buy to Cover)

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            quantity: 수량
            order_type: 주문 유형 (MARKET 또는 LIMIT)
            limit_price: 지정가 (LIMIT 주문인 경우)

        Returns:
            주문 결과
        """
        order_spec = {
            "orderType": order_type.value,
            "session": Session.NORMAL.value,
            "duration": Duration.DAY.value,
            "orderStrategyType": OrderStrategyType.SINGLE.value,
            "orderLegCollection": [
                {
                    "instruction": OrderSide.BUY_TO_COVER.value,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": AssetType.EQUITY.value
                    }
                }
            ]
        }

        if order_type == OrderType.LIMIT and limit_price is not None:
            order_spec["price"] = str(limit_price)

        return await self._place_order(
            account_hash,
            order_spec,
            f"buy_to_cover_{order_type.value.lower()}"
        )

    # OCO (One Cancels Other) Orders Implementation
    async def create_oco_order(
        self,
        account_hash: str,
        symbol: str,
        quantity: int,
        primary_order_type: OrderType,
        secondary_order_type: OrderType,
        primary_price: Optional[float] = None,
        secondary_price: Optional[float] = None,
        primary_instruction: str = "BUY",
        secondary_instruction: str = "SELL"
    ) -> Dict[str, Any]:
        """
        OCO (One Cancels Other) 주문 생성

        한 주문이 체결되면 다른 주문이 자동으로 취소되는 복합 주문

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            quantity: 수량
            primary_order_type: 주 주문 타입
            secondary_order_type: 보조 주문 타입
            primary_price: 주 주문 가격
            secondary_price: 보조 주문 가격
            primary_instruction: 주 주문 지시 (BUY/SELL)
            secondary_instruction: 보조 주문 지시 (BUY/SELL)
        """
        try:
            order_spec = {
                "orderType": "OCO",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": ComplexOrderStrategyType.OCO.value,
                "childOrderStrategies": [
                    {
                        "orderType": primary_order_type.value,
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [
                            {
                                "instruction": primary_instruction,
                                "quantity": quantity,
                                "instrument": {
                                    "symbol": symbol,
                                    "assetType": "EQUITY"
                                }
                            }
                        ]
                    },
                    {
                        "orderType": secondary_order_type.value,
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [
                            {
                                "instruction": secondary_instruction,
                                "quantity": quantity,
                                "instrument": {
                                    "symbol": symbol,
                                    "assetType": "EQUITY"
                                }
                            }
                        ]
                    }
                ]
            }

            # 가격 설정
            if primary_price is not None and primary_order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                order_spec["childOrderStrategies"][0]["price"] = str(primary_price)

            if secondary_price is not None and secondary_order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                order_spec["childOrderStrategies"][1]["price"] = str(secondary_price)

            # Stop 가격 설정
            if primary_order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and primary_price is not None:
                order_spec["childOrderStrategies"][0]["stopPrice"] = str(primary_price)

            if secondary_order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and secondary_price is not None:
                order_spec["childOrderStrategies"][1]["stopPrice"] = str(secondary_price)

            return await self._place_order(account_hash, order_spec, "oco_order")

        except Exception as e:
            logger.error(f"OCO 주문 생성 실패: {e}")
            raise TradingException(f"OCO 주문 생성 실패: {e}")

    # OTO (One Triggers Other) Orders Implementation
    async def create_oto_order(
        self,
        account_hash: str,
        symbol: str,
        trigger_quantity: int,
        trigger_order_type: OrderType,
        trigger_price: Optional[float],
        trigger_instruction: str,
        target_quantity: int,
        target_order_type: OrderType,
        target_price: Optional[float],
        target_instruction: str
    ) -> Dict[str, Any]:
        """
        OTO (One Triggers Other) 주문 생성

        첫 번째 주문이 체결되면 두 번째 주문이 자동으로 활성화되는 복합 주문

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            trigger_quantity: 트리거 주문 수량
            trigger_order_type: 트리거 주문 타입
            trigger_price: 트리거 주문 가격
            trigger_instruction: 트리거 주문 지시
            target_quantity: 타겟 주문 수량
            target_order_type: 타겟 주문 타입
            target_price: 타겟 주문 가격
            target_instruction: 타겟 주문 지시
        """
        try:
            order_spec = {
                "orderType": "TRIGGER",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": ComplexOrderStrategyType.OTO.value,
                "orderLegCollection": [
                    {
                        "instruction": trigger_instruction,
                        "quantity": trigger_quantity,
                        "instrument": {
                            "symbol": symbol,
                            "assetType": "EQUITY"
                        }
                    }
                ],
                "childOrderStrategies": [
                    {
                        "orderType": target_order_type.value,
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [
                            {
                                "instruction": target_instruction,
                                "quantity": target_quantity,
                                "instrument": {
                                    "symbol": symbol,
                                    "assetType": "EQUITY"
                                }
                            }
                        ]
                    }
                ]
            }

            # 트리거 주문 가격 설정
            if trigger_price is not None:
                if trigger_order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                    order_spec["price"] = str(trigger_price)
                if trigger_order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
                    order_spec["stopPrice"] = str(trigger_price)

            # 타겟 주문 가격 설정
            if target_price is not None:
                if target_order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                    order_spec["childOrderStrategies"][0]["price"] = str(target_price)
                if target_order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
                    order_spec["childOrderStrategies"][0]["stopPrice"] = str(target_price)

            return await self._place_order(account_hash, order_spec, "oto_order")

        except Exception as e:
            logger.error(f"OTO 주문 생성 실패: {e}")
            raise TradingException(f"OTO 주문 생성 실패: {e}")

    # Bracket Orders Implementation
    async def create_bracket_order(
        self,
        account_hash: str,
        symbol: str,
        quantity: int,
        entry_order_type: OrderType,
        entry_price: Optional[float],
        take_profit_price: float,
        stop_loss_price: float,
        instruction: str = "BUY"
    ) -> Dict[str, Any]:
        """
        브래킷 주문 생성 (Entry + Take Profit + Stop Loss)

        진입 주문과 동시에 수익실현 및 손절 주문을 함께 설정하는 복합 주문

        Args:
            account_hash: 계좌 해시
            symbol: 심볼
            quantity: 수량
            entry_order_type: 진입 주문 타입
            entry_price: 진입 가격
            take_profit_price: 수익실현 가격
            stop_loss_price: 손절 가격
            instruction: 진입 지시 (BUY/SELL)
        """
        try:
            # 브래킷 주문은 OTO + OCO 조합으로 구현
            # 1. 진입 주문이 체결되면 (OTO)
            # 2. 수익실현과 손절 주문이 동시에 활성화되고 (OCO)
            # 3. 둘 중 하나가 체결되면 다른 하나는 취소

            exit_instruction = "SELL" if instruction == "BUY" else "BUY"

            order_spec = {
                "orderType": "TRIGGER",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": ComplexOrderStrategyType.BRACKET.value,
                "orderLegCollection": [
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": symbol,
                            "assetType": "EQUITY"
                        }
                    }
                ],
                "childOrderStrategies": [
                    {
                        "orderType": "OCO",
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderStrategyType": ComplexOrderStrategyType.OCO.value,
                        "childOrderStrategies": [
                            {
                                # Take Profit Order
                                "orderType": "LIMIT",
                                "session": "NORMAL",
                                "duration": "DAY",
                                "orderStrategyType": "SINGLE",
                                "price": str(take_profit_price),
                                "orderLegCollection": [
                                    {
                                        "instruction": exit_instruction,
                                        "quantity": quantity,
                                        "instrument": {
                                            "symbol": symbol,
                                            "assetType": "EQUITY"
                                        }
                                    }
                                ]
                            },
                            {
                                # Stop Loss Order
                                "orderType": "STOP",
                                "session": "NORMAL",
                                "duration": "DAY",
                                "orderStrategyType": "SINGLE",
                                "stopPrice": str(stop_loss_price),
                                "orderLegCollection": [
                                    {
                                        "instruction": exit_instruction,
                                        "quantity": quantity,
                                        "instrument": {
                                            "symbol": symbol,
                                            "assetType": "EQUITY"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }

            # 진입 주문 가격 설정
            if entry_price is not None:
                if entry_order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                    order_spec["price"] = str(entry_price)
                if entry_order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
                    order_spec["stopPrice"] = str(entry_price)

            return await self._place_order(account_hash, order_spec, "bracket_order")

        except Exception as e:
            logger.error(f"브래킷 주문 생성 실패: {e}")
            raise TradingException(f"브래킷 주문 생성 실패: {e}")

    # Options Trading Implementation
    async def create_options_order(
        self,
        account_hash: str,
        option_symbol: str,
        quantity: int,
        instruction: str,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        time_in_force: str = "DAY"
    ) -> Dict[str, Any]:
        """
        옵션 주문 생성

        Args:
            account_hash: 계좌 해시
            option_symbol: 옵션 심볼 (예: AAPL_012025C150)
            quantity: 계약 수량
            instruction: 주문 지시 (BUY_TO_OPEN, SELL_TO_CLOSE, etc.)
            order_type: 주문 타입
            price: 가격 (LIMIT 주문시)
            time_in_force: 주문 유효기간
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": time_in_force,
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": option_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and price is not None:
                order_spec["price"] = str(price)

            return await self._place_order(
                account_hash,
                order_spec,
                f"options_{instruction.lower()}"
            )

        except Exception as e:
            logger.error(f"옵션 주문 생성 실패: {e}")
            raise TradingException(f"옵션 주문 생성 실패: {e}")

    async def create_covered_call(
        self,
        account_hash: str,
        underlying_symbol: str,
        option_symbol: str,
        quantity: int,
        call_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        커버드 콜 전략 (보유 주식 + 콜 옵션 매도)

        Args:
            account_hash: 계좌 해시
            underlying_symbol: 기초자산 심볼
            option_symbol: 콜 옵션 심볼
            quantity: 옵션 계약 수량 (주식 100주당 1계약)
            call_price: 콜 옵션 매도 가격
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "COVERED",
                "orderLegCollection": [
                    {
                        "instruction": "SELL_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": option_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and call_price is not None:
                order_spec["price"] = str(call_price)

            return await self._place_order(account_hash, order_spec, "covered_call")

        except Exception as e:
            logger.error(f"커버드 콜 생성 실패: {e}")
            raise TradingException(f"커버드 콜 생성 실패: {e}")

    async def create_protective_put(
        self,
        account_hash: str,
        underlying_symbol: str,
        option_symbol: str,
        quantity: int,
        put_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        보호 풋 전략 (보유 주식 + 풋 옵션 매수)

        Args:
            account_hash: 계좌 해시
            underlying_symbol: 기초자산 심볼
            option_symbol: 풋 옵션 심볼
            quantity: 옵션 계약 수량
            put_price: 풋 옵션 매수 가격
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "PROTECTIVE",
                "orderLegCollection": [
                    {
                        "instruction": "BUY_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": option_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and put_price is not None:
                order_spec["price"] = str(put_price)

            return await self._place_order(account_hash, order_spec, "protective_put")

        except Exception as e:
            logger.error(f"보호 풋 생성 실패: {e}")
            raise TradingException(f"보호 풋 생성 실패: {e}")

    async def create_straddle(
        self,
        account_hash: str,
        call_symbol: str,
        put_symbol: str,
        quantity: int,
        instruction: str = "BUY_TO_OPEN",
        net_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        스트래들 전략 (동일 행사가격 콜+풋 매수/매도)

        Args:
            account_hash: 계좌 해시
            call_symbol: 콜 옵션 심볼
            put_symbol: 풋 옵션 심볼
            quantity: 계약 수량
            instruction: 주문 지시 (BUY_TO_OPEN/SELL_TO_OPEN)
            net_price: 네트 가격 (프리미엄 총합)
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "STRADDLE",
                "orderLegCollection": [
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": call_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": put_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and net_price is not None:
                order_spec["price"] = str(net_price)

            return await self._place_order(account_hash, order_spec, "straddle")

        except Exception as e:
            logger.error(f"스트래들 생성 실패: {e}")
            raise TradingException(f"스트래들 생성 실패: {e}")

    async def create_strangle(
        self,
        account_hash: str,
        call_symbol: str,
        put_symbol: str,
        quantity: int,
        instruction: str = "BUY_TO_OPEN",
        net_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        스트랭글 전략 (서로 다른 행사가격 콜+풋 매수/매도)

        Args:
            account_hash: 계좌 해시
            call_symbol: 콜 옵션 심볼 (높은 행사가격)
            put_symbol: 풋 옵션 심볼 (낮은 행사가격)
            quantity: 계약 수량
            instruction: 주문 지시 (BUY_TO_OPEN/SELL_TO_OPEN)
            net_price: 네트 가격
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "STRANGLE",
                "orderLegCollection": [
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": call_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": instruction,
                        "quantity": quantity,
                        "instrument": {
                            "symbol": put_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and net_price is not None:
                order_spec["price"] = str(net_price)

            return await self._place_order(account_hash, order_spec, "strangle")

        except Exception as e:
            logger.error(f"스트랭글 생성 실패: {e}")
            raise TradingException(f"스트랭글 생성 실패: {e}")

    async def create_vertical_spread(
        self,
        account_hash: str,
        long_option_symbol: str,
        short_option_symbol: str,
        quantity: int,
        spread_type: str = "CALL",
        net_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        수직 스프레드 전략 (콜 스프레드 또는 풋 스프레드)

        Args:
            account_hash: 계좌 해시
            long_option_symbol: 매수할 옵션 심볼
            short_option_symbol: 매도할 옵션 심볼
            quantity: 계약 수량
            spread_type: 스프레드 타입 (CALL/PUT)
            net_price: 네트 가격 (데빗/크레딧)
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "VERTICAL",
                "orderLegCollection": [
                    {
                        "instruction": "BUY_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": long_option_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": "SELL_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": short_option_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and net_price is not None:
                order_spec["price"] = str(net_price)

            return await self._place_order(account_hash, order_spec, f"vertical_{spread_type.lower()}")

        except Exception as e:
            logger.error(f"수직 스프레드 생성 실패: {e}")
            raise TradingException(f"수직 스프레드 생성 실패: {e}")

    async def create_iron_condor(
        self,
        account_hash: str,
        put_buy_symbol: str,
        put_sell_symbol: str,
        call_sell_symbol: str,
        call_buy_symbol: str,
        quantity: int,
        net_credit: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict[str, Any]:
        """
        아이언 콘도르 전략 (4개 옵션 조합)

        Args:
            account_hash: 계좌 해시
            put_buy_symbol: 매수할 풋 옵션 (낮은 행사가)
            put_sell_symbol: 매도할 풋 옵션 (높은 행사가)
            call_sell_symbol: 매도할 콜 옵션 (낮은 행사가)
            call_buy_symbol: 매수할 콜 옵션 (높은 행사가)
            quantity: 계약 수량
            net_credit: 네트 크레딧
            order_type: 주문 타입
        """
        try:
            order_spec = {
                "orderType": order_type.value,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "IRON_CONDOR",
                "orderLegCollection": [
                    {
                        "instruction": "BUY_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": put_buy_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": "SELL_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": put_sell_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": "SELL_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": call_sell_symbol,
                            "assetType": "OPTION"
                        }
                    },
                    {
                        "instruction": "BUY_TO_OPEN",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": call_buy_symbol,
                            "assetType": "OPTION"
                        }
                    }
                ]
            }

            if order_type == OrderType.LIMIT and net_credit is not None:
                order_spec["price"] = str(net_credit)

            return await self._place_order(account_hash, order_spec, "iron_condor")

        except Exception as e:
            logger.error(f"아이언 콘도르 생성 실패: {e}")
            raise TradingException(f"아이언 콘도르 생성 실패: {e}")

    # Advanced Order Management Implementation
    async def cancel_order(
        self,
        account_hash: str,
        order_id: str
    ) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            account_hash: 계좌 해시
            order_id: 주문 ID

        Returns:
            취소 결과
        """
        try:
            logger.info(f"주문 취소 시도: {order_id}")

            # Schwab API 호출하여 주문 취소
            response = await self._execute_with_resilience(
                f"cancel_order_{order_id}",
                lambda: self.schwab_service.client.cancel_order(account_hash, order_id)
            )

            result = {
                'status': 'success',
                'order_id': order_id,
                'message': 'Order cancelled successfully'
            }

            if hasattr(response, 'status_code'):
                result['status_code'] = response.status_code

            logger.info(f"주문 취소 완료: {order_id}")
            return result

        except Exception as e:
            logger.error(f"주문 취소 실패 {order_id}: {e}")
            raise TradingException(f"주문 취소 실패: {e}")

    async def replace_order(
        self,
        account_hash: str,
        order_id: str,
        new_order_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        주문 수정 (Replace)

        Args:
            account_hash: 계좌 해시
            order_id: 수정할 주문 ID
            new_order_spec: 새로운 주문 사양

        Returns:
            수정 결과
        """
        try:
            logger.info(f"주문 수정 시도: {order_id}")

            response = await self._execute_with_resilience(
                f"replace_order_{order_id}",
                lambda: self.schwab_service.client.replace_order(
                    account_hash, order_id, new_order_spec
                )
            )

            result = {
                'status': 'success',
                'original_order_id': order_id,
                'message': 'Order replaced successfully'
            }

            if hasattr(response, 'status_code'):
                result['status_code'] = response.status_code

                # 새 주문 ID 추출 시도
                if response.status_code == 201 and hasattr(response, 'headers'):
                    location = response.headers.get('Location', '')
                    if '/orders/' in location:
                        new_order_id = location.split('/orders/')[-1]
                        result['new_order_id'] = new_order_id

            logger.info(f"주문 수정 완료: {order_id}")
            return result

        except Exception as e:
            logger.error(f"주문 수정 실패 {order_id}: {e}")
            raise TradingException(f"주문 수정 실패: {e}")

    async def get_orders(
        self,
        account_hash: str,
        max_results: int = 50,
        from_entered_time: Optional[str] = None,
        to_entered_time: Optional[str] = None,
        status_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        주문 목록 조회

        Args:
            account_hash: 계좌 해시
            max_results: 최대 결과 수
            from_entered_time: 시작 시간 (ISO format)
            to_entered_time: 종료 시간 (ISO format)
            status_filter: 상태 필터 (WORKING, FILLED, CANCELED, etc.)

        Returns:
            주문 목록
        """
        try:
            logger.info(f"주문 목록 조회: account={account_hash}, max={max_results}")

            # 파라미터 구성
            params = {
                'maxResults': max_results
            }

            if from_entered_time:
                params['fromEnteredTime'] = from_entered_time
            if to_entered_time:
                params['toEnteredTime'] = to_entered_time
            if status_filter:
                params['status'] = status_filter

            orders = await self._execute_with_resilience(
                f"get_orders_{account_hash}",
                lambda: self.schwab_service.client.get_orders_for_account(
                    account_hash, **params
                )
            )

            order_data = orders.json() if hasattr(orders, 'json') else orders

            # 주문 데이터 정리
            if isinstance(order_data, list):
                processed_orders = []
                for order in order_data:
                    processed_order = {
                        'orderId': order.get('orderId'),
                        'enteredTime': order.get('enteredTime'),
                        'status': order.get('status'),
                        'orderType': order.get('orderType'),
                        'quantity': order.get('quantity'),
                        'filledQuantity': order.get('filledQuantity'),
                        'price': order.get('price'),
                        'stopPrice': order.get('stopPrice'),
                        'orderLegCollection': order.get('orderLegCollection', [])
                    }
                    processed_orders.append(processed_order)

                return {
                    'status': 'success',
                    'orders': processed_orders,
                    'count': len(processed_orders)
                }
            else:
                return {
                    'status': 'success',
                    'orders': [],
                    'count': 0
                }

        except Exception as e:
            logger.error(f"주문 목록 조회 실패: {e}")
            raise TradingException(f"주문 목록 조회 실패: {e}")

    async def get_order_by_id(
        self,
        account_hash: str,
        order_id: str
    ) -> Dict[str, Any]:
        """
        특정 주문 상세 조회

        Args:
            account_hash: 계좌 해시
            order_id: 주문 ID

        Returns:
            주문 상세 정보
        """
        try:
            logger.info(f"주문 상세 조회: {order_id}")

            order = await self._execute_with_resilience(
                f"get_order_{order_id}",
                lambda: self.schwab_service.client.get_order(account_hash, order_id)
            )

            order_data = order.json() if hasattr(order, 'json') else order

            return {
                'status': 'success',
                'order': order_data
            }

        except Exception as e:
            logger.error(f"주문 상세 조회 실패 {order_id}: {e}")
            raise TradingException(f"주문 상세 조회 실패: {e}")

    async def get_orders_by_path(
        self,
        account_hash: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        날짜 범위별 주문 조회

        Args:
            account_hash: 계좌 해시
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)

        Returns:
            기간별 주문 목록
        """
        try:
            logger.info(f"기간별 주문 조회: {start_date} ~ {end_date}")

            orders = await self._execute_with_resilience(
                f"get_orders_by_path_{start_date}_{end_date}",
                lambda: self.schwab_service.client.get_orders_by_path(
                    account_hash, start_date, end_date
                )
            )

            order_data = orders.json() if hasattr(orders, 'json') else orders

            return {
                'status': 'success',
                'orders': order_data if isinstance(order_data, list) else [],
                'period': f"{start_date} to {end_date}"
            }

        except Exception as e:
            logger.error(f"기간별 주문 조회 실패: {e}")
            raise TradingException(f"기간별 주문 조회 실패: {e}")

    # Price History Service Implementation
    async def get_price_history(
        self,
        symbol: str,
        period_type: str = "day",
        period: int = 1,
        frequency_type: str = "minute",
        frequency: int = 1,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        need_extended_hours_data: bool = False
    ) -> Dict[str, Any]:
        """
        가격 히스토리 조회

        Args:
            symbol: 심볼
            period_type: 기간 타입 (day, month, year, ytd)
            period: 기간
            frequency_type: 빈도 타입 (minute, daily, weekly, monthly)
            frequency: 빈도
            start_date: 시작 날짜 (epoch time)
            end_date: 종료 날짜 (epoch time)
            need_extended_hours_data: 시간외 거래 데이터 포함 여부

        Returns:
            가격 히스토리 데이터
        """
        try:
            logger.info(f"가격 히스토리 조회: {symbol}")

            # Schwab API 클라이언트 직접 호출
            price_history = await self._execute_with_resilience(
                f"get_price_history_{symbol}",
                lambda: self.schwab_service.client.get_price_history(
                    symbol=symbol,
                    period_type=period_type,
                    period=period,
                    frequency_type=frequency_type,
                    frequency=frequency,
                    start_date=start_date,
                    end_date=end_date,
                    need_extended_hours_data=need_extended_hours_data
                )
            )

            history_data = price_history.json() if hasattr(price_history, 'json') else price_history

            return {
                'status': 'success',
                'symbol': symbol,
                'data': history_data
            }

        except Exception as e:
            logger.error(f"가격 히스토리 조회 실패 {symbol}: {e}")
            raise TradingException(f"가격 히스토리 조회 실패: {e}")

    async def get_option_chain(
        self,
        symbol: str,
        contract_type: str = "ALL",
        strike_count: int = 10,
        include_quotes: bool = False,
        strategy: str = "SINGLE",
        interval: Optional[float] = None,
        strike: Optional[float] = None,
        range_value: str = "ALL",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        volatility: Optional[float] = None,
        underlying_price: Optional[float] = None,
        interest_rate: Optional[float] = None,
        days_to_expiration: Optional[int] = None,
        exp_month: str = "ALL",
        option_type: str = "S"
    ) -> Dict[str, Any]:
        """
        옵션 체인 조회

        Args:
            symbol: 기초자산 심볼
            contract_type: 계약 타입 (CALL, PUT, ALL)
            strike_count: 행사가격 개수
            include_quotes: 시세 포함 여부
            strategy: 전략 (SINGLE, ANALYTICAL, COVERED, VERTICAL, etc.)
            interval: 행사가격 간격
            strike: 특정 행사가격
            range_value: 범위 (ITM, NTM, OTM, SAK, SBK, SNK, ALL)
            from_date: 시작 만료일
            to_date: 종료 만료일
            volatility: 변동성
            underlying_price: 기초자산 가격
            interest_rate: 이자율
            days_to_expiration: 만료까지 일수
            exp_month: 만료월 (JAN, FEB, ..., ALL)
            option_type: 옵션 타입 (S=Standard, NS=Non-Standard)

        Returns:
            옵션 체인 데이터
        """
        try:
            logger.info(f"옵션 체인 조회: {symbol}")

            option_chain = await self._execute_with_resilience(
                f"get_option_chain_{symbol}",
                lambda: self.schwab_service.client.get_option_chain(
                    symbol=symbol,
                    contract_type=contract_type,
                    strike_count=strike_count,
                    include_quotes=include_quotes,
                    strategy=strategy,
                    interval=interval,
                    strike=strike,
                    range_value=range_value,
                    from_date=from_date,
                    to_date=to_date,
                    volatility=volatility,
                    underlying_price=underlying_price,
                    interest_rate=interest_rate,
                    days_to_expiration=days_to_expiration,
                    exp_month=exp_month,
                    option_type=option_type
                )
            )

            chain_data = option_chain.json() if hasattr(option_chain, 'json') else option_chain

            return {
                'status': 'success',
                'symbol': symbol,
                'option_chain': chain_data
            }

        except Exception as e:
            logger.error(f"옵션 체인 조회 실패 {symbol}: {e}")
            raise TradingException(f"옵션 체인 조회 실패: {e}")

    # Streaming Data Service Implementation
    async def start_streaming(
        self,
        symbols: List[str],
        fields: List[str] = None,
        service: str = "CHART_EQUITY"
    ) -> Dict[str, Any]:
        """
        실시간 스트리밍 데이터 시작

        Args:
            symbols: 구독할 심볼 목록
            fields: 구독할 필드 목록
            service: 서비스 타입 (CHART_EQUITY, QUOTE, TIMESALE_EQUITY, etc.)

        Returns:
            스트리밍 시작 결과
        """
        try:
            logger.info(f"스트리밍 시작: {symbols}, service={service}")

            # 기본 필드 설정
            if fields is None:
                if service == "CHART_EQUITY":
                    fields = ["key", "timestamp", "open", "high", "low", "close", "volume"]
                elif service == "QUOTE":
                    fields = ["key", "assetMainType", "assetSubType", "bidPrice", "askPrice",
                             "lastPrice", "bidSize", "askSize", "totalVolume", "quoteTime", "tradeTime"]
                elif service == "TIMESALE_EQUITY":
                    fields = ["key", "tradeTime", "lastPrice", "lastSize", "totalVolume"]
                else:
                    fields = ["key"]

            # 스트리밍 설정
            streaming_config = {
                "service": service,
                "command": "SUBS",
                "requestid": "1",
                "SchwabClientCustomerId": self.schwab_service.client.get_client_id(),
                "SchwabClientCorrelId": str(hash(f"{service}_{symbols[0]}")),
                "parameters": {
                    "keys": ",".join(symbols),
                    "fields": ",".join(fields)
                }
            }

            result = {
                'status': 'success',
                'message': 'Streaming configuration prepared',
                'service': service,
                'symbols': symbols,
                'fields': fields,
                'config': streaming_config
            }

            logger.info(f"스트리밍 구성 완료: {service}")
            return result

        except Exception as e:
            logger.error(f"스트리밍 시작 실패: {e}")
            raise TradingException(f"스트리밍 시작 실패: {e}")

    async def stop_streaming(
        self,
        symbols: List[str] = None,
        service: str = "CHART_EQUITY"
    ) -> Dict[str, Any]:
        """
        실시간 스트리밍 데이터 중지

        Args:
            symbols: 구독 해제할 심볼 목록 (None이면 전체)
            service: 서비스 타입

        Returns:
            스트리밍 중지 결과
        """
        try:
            logger.info(f"스트리밍 중지: {symbols}, service={service}")

            # 스트리밍 중지 설정
            streaming_config = {
                "service": service,
                "command": "UNSUBS",
                "requestid": "2",
                "SchwabClientCustomerId": self.schwab_service.client.get_client_id(),
                "SchwabClientCorrelId": str(hash(f"stop_{service}")),
                "parameters": {
                    "keys": ",".join(symbols) if symbols else "",
                }
            }

            result = {
                'status': 'success',
                'message': 'Streaming stop configuration prepared',
                'service': service,
                'symbols': symbols or [],
                'config': streaming_config
            }

            logger.info(f"스트리밍 중지 구성 완료: {service}")
            return result

        except Exception as e:
            logger.error(f"스트리밍 중지 실패: {e}")
            raise TradingException(f"스트리밍 중지 실패: {e}")

    async def get_streaming_data(
        self,
        service: str = "CHART_EQUITY",
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        스트리밍 데이터 수신

        Args:
            service: 서비스 타입
            timeout: 타임아웃 (초)

        Returns:
            스트리밍 데이터
        """
        try:
            logger.info(f"스트리밍 데이터 수신 대기: {service}")

            # 실제 구현에서는 WebSocket이나 다른 스트리밍 프로토콜 사용
            # 여기서는 구조만 제공
            streaming_data = {
                'service': service,
                'timestamp': int(time.time() * 1000),
                'data': [],
                'status': 'connected'
            }

            result = {
                'status': 'success',
                'streaming_data': streaming_data,
                'timeout': timeout
            }

            logger.info(f"스트리밍 데이터 구조 준비 완료: {service}")
            return result

        except Exception as e:
            logger.error(f"스트리밍 데이터 수신 실패: {e}")
            raise TradingException(f"스트리밍 데이터 수신 실패: {e}")

    # Portfolio and Account Information
    async def get_positions(
        self,
        account_hash: str
    ) -> Dict[str, Any]:
        """
        포지션 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            포지션 목록
        """
        try:
            logger.info(f"포지션 조회: {account_hash}")

            account_info = await self.schwab_service.get_account_info(account_hash)

            positions = []
            if 'securitiesAccount' in account_info:
                account_positions = account_info['securitiesAccount'].get('positions', [])

                for position in account_positions:
                    instrument = position.get('instrument', {})
                    processed_position = {
                        'symbol': instrument.get('symbol'),
                        'assetType': instrument.get('assetType'),
                        'longQuantity': position.get('longQuantity', 0),
                        'shortQuantity': position.get('shortQuantity', 0),
                        'averagePrice': position.get('averagePrice', 0),
                        'currentDayProfitLoss': position.get('currentDayProfitLoss', 0),
                        'marketValue': position.get('marketValue', 0)
                    }
                    positions.append(processed_position)

            return {
                'status': 'success',
                'account_hash': account_hash,
                'positions': positions,
                'count': len(positions)
            }

        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            raise TradingException(f"포지션 조회 실패: {e}")

    async def get_balance(
        self,
        account_hash: str
    ) -> Dict[str, Any]:
        """
        계좌 잔고 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            잔고 정보
        """
        try:
            logger.info(f"잔고 조회: {account_hash}")

            account_info = await self.schwab_service.get_account_info(account_hash)

            balance_info = {}
            if 'securitiesAccount' in account_info:
                balances = account_info['securitiesAccount'].get('currentBalances', {})
                balance_info = {
                    'liquidationValue': balances.get('liquidationValue', 0),
                    'longMarketValue': balances.get('longMarketValue', 0),
                    'shortMarketValue': balances.get('shortMarketValue', 0),
                    'availableFunds': balances.get('availableFunds', 0),
                    'buyingPower': balances.get('buyingPower', 0),
                    'dayTradingBuyingPower': balances.get('dayTradingBuyingPower', 0),
                    'cashBalance': balances.get('cashBalance', 0),
                    'marginBalance': balances.get('marginBalance', 0),
                    'totalCash': balances.get('totalCash', 0)
                }

            return {
                'status': 'success',
                'account_hash': account_hash,
                'balances': balance_info
            }

        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            raise TradingException(f"잔고 조회 실패: {e}")

    async def get_transactions(
        self,
        account_hash: str,
        transaction_type: str = "ALL",
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        거래 내역 조회

        Args:
            account_hash: 계좌 해시
            transaction_type: 거래 타입 (ALL, TRADE, BUY_ONLY, SELL_ONLY, etc.)
            symbol: 특정 심볼
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)

        Returns:
            거래 내역
        """
        try:
            logger.info(f"거래 내역 조회: {account_hash}")

            transactions = await self._execute_with_resilience(
                f"get_transactions_{account_hash}",
                lambda: self.schwab_service.client.get_transactions(
                    account_hash,
                    transaction_type=transaction_type,
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
            )

            transaction_data = transactions.json() if hasattr(transactions, 'json') else transactions

            return {
                'status': 'success',
                'account_hash': account_hash,
                'transactions': transaction_data if isinstance(transaction_data, list) else [],
                'count': len(transaction_data) if isinstance(transaction_data, list) else 0
            }

        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {e}")
            raise TradingException(f"거래 내역 조회 실패: {e}")

    # Utility and Helper Methods
    async def get_market_movers(
        self,
        index: str = "$DJI",
        direction: str = "up",
        change: str = "percent"
    ) -> Dict[str, Any]:
        """
        시장 주요 변동 종목 조회

        Args:
            index: 지수 ($DJI, $COMPX, $SPX.X)
            direction: 방향 (up, down)
            change: 변동 기준 (percent, value)

        Returns:
            시장 주요 변동 종목
        """
        try:
            logger.info(f"시장 주요 변동 종목 조회: {index}")

            movers = await self._execute_with_resilience(
                f"get_market_movers_{index}",
                lambda: self.schwab_service.client.get_market_movers(
                    index, direction=direction, change=change
                )
            )

            movers_data = movers.json() if hasattr(movers, 'json') else movers

            return {
                'status': 'success',
                'index': index,
                'direction': direction,
                'change': change,
                'movers': movers_data
            }

        except Exception as e:
            logger.error(f"시장 주요 변동 종목 조회 실패: {e}")
            raise TradingException(f"시장 주요 변동 종목 조회 실패: {e}")

    async def search_instruments(
        self,
        symbol: str,
        projection: str = "symbol-search"
    ) -> Dict[str, Any]:
        """
        금융상품 검색

        Args:
            symbol: 검색할 심볼
            projection: 검색 타입 (symbol-search, symbol-regex, desc-search, etc.)

        Returns:
            검색 결과
        """
        try:
            logger.info(f"금융상품 검색: {symbol}")

            instruments = await self._execute_with_resilience(
                f"search_instruments_{symbol}",
                lambda: self.schwab_service.client.search_instruments(
                    symbol, projection=projection
                )
            )

            instruments_data = instruments.json() if hasattr(instruments, 'json') else instruments

            return {
                'status': 'success',
                'symbol': symbol,
                'projection': projection,
                'instruments': instruments_data
            }

        except Exception as e:
            logger.error(f"금융상품 검색 실패: {e}")
            raise TradingException(f"금융상품 검색 실패: {e}")

    async def get_fundamentals(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """
        기업 기본 정보 조회

        Args:
            symbol: 심볼

        Returns:
            기업 기본 정보
        """
        try:
            logger.info(f"기업 기본 정보 조회: {symbol}")

            fundamentals = await self._execute_with_resilience(
                f"get_fundamentals_{symbol}",
                lambda: self.schwab_service.client.get_instrument(symbol)
            )

            fundamentals_data = fundamentals.json() if hasattr(fundamentals, 'json') else fundamentals

            return {
                'status': 'success',
                'symbol': symbol,
                'fundamentals': fundamentals_data
            }

        except Exception as e:
            logger.error(f"기업 기본 정보 조회 실패: {e}")
            raise TradingException(f"기업 기본 정보 조회 실패: {e}")