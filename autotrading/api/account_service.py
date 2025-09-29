"""
Account Service

계좌 정보 조회 및 관리를 담당하는 서비스입니다.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from .schwab_service import SchwabAPIService, SchwabAPIException

logger = logging.getLogger(__name__)


class AccountException(Exception):
    """계좌 관련 예외"""
    pass


class AccountService:
    """
    계좌 서비스

    Schwab API를 통해 계좌 정보 조회 및 관리를 담당하는 서비스입니다.
    다음 기능을 제공합니다:
    - 계좌 정보 조회
    - 잔고 및 포지션 조회
    - 거래 히스토리 조회
    - 계좌 성과 분석
    """

    def __init__(self, schwab_service: SchwabAPIService):
        """
        Account Service 초기화

        Args:
            schwab_service: Schwab API 서비스 인스턴스
        """
        self.schwab_service = schwab_service
        self.logger = logging.getLogger(__name__)

    async def get_account_summary(self, account_hash: str) -> Dict[str, Any]:
        """
        계좌 요약 정보 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            계좌 요약 정보
        """
        try:
            logger.debug(f"Getting account summary for {account_hash}")

            account_info = await self.schwab_service.get_account_info(account_hash)

            if not account_info or "securitiesAccount" not in account_info:
                raise AccountException("Invalid account info received")

            securities_account = account_info["securitiesAccount"]

            summary = self._process_account_summary(securities_account, account_hash)

            logger.debug(f"Account summary retrieved for {account_hash}")
            return summary

        except Exception as e:
            logger.error(f"Failed to get account summary for {account_hash}: {e}")
            raise AccountException(f"Failed to get account summary: {e}")

    def _process_account_summary(
        self,
        securities_account: Dict[str, Any],
        account_hash: str
    ) -> Dict[str, Any]:
        """계좌 요약 정보 처리"""
        current_balances = securities_account.get("currentBalances", {})
        initial_balances = securities_account.get("initialBalances", {})

        summary = {
            "account_hash": account_hash,
            "account_number": securities_account.get("accountNumber", ""),
            "account_type": securities_account.get("type", ""),
            "timestamp": datetime.now(timezone.utc),

            # 잔고 정보
            "total_value": current_balances.get("liquidationValue", 0.0),
            "cash_balance": current_balances.get("cashBalance", 0.0),
            "available_funds": current_balances.get("availableFunds", 0.0),
            "buying_power": current_balances.get("buyingPower", 0.0),
            "equity_value": current_balances.get("equity", 0.0),
            "long_market_value": current_balances.get("longMarketValue", 0.0),
            "short_market_value": current_balances.get("shortMarketValue", 0.0),

            # 일일 변화
            "day_gain_loss": current_balances.get("totalLongValue", 0.0) -
                           initial_balances.get("totalLongValue", 0.0),
            "day_gain_loss_percent": self._calculate_percent_change(
                initial_balances.get("totalLongValue", 0.0),
                current_balances.get("totalLongValue", 0.0)
            ),

            # 기타 정보
            "is_day_trader": securities_account.get("isDayTrader", False),
            "is_closing_only_restricted": securities_account.get("isClosingOnlyRestricted", False),
        }

        return summary

    def _calculate_percent_change(self, initial: float, current: float) -> float:
        """퍼센트 변화 계산"""
        if initial == 0:
            return 0.0
        return ((current - initial) / initial) * 100.0

    async def get_positions(self, account_hash: str) -> List[Dict[str, Any]]:
        """
        포지션 목록 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            포지션 목록
        """
        try:
            logger.debug(f"Getting positions for {account_hash}")

            account_info = await self.schwab_service.get_account_info(account_hash)

            if not account_info or "securitiesAccount" not in account_info:
                raise AccountException("Invalid account info received")

            positions_data = account_info["securitiesAccount"].get("positions", [])

            positions = []
            for position_data in positions_data:
                position = self._process_position_data(position_data, account_hash)
                if position:
                    positions.append(position)

            logger.debug(f"Retrieved {len(positions)} positions for {account_hash}")
            return positions

        except Exception as e:
            logger.error(f"Failed to get positions for {account_hash}: {e}")
            raise AccountException(f"Failed to get positions: {e}")

    def _process_position_data(
        self,
        position_data: Dict[str, Any],
        account_hash: str
    ) -> Optional[Dict[str, Any]]:
        """포지션 데이터 처리"""
        try:
            instrument = position_data.get("instrument", {})

            position = {
                "account_hash": account_hash,
                "symbol": instrument.get("symbol", ""),
                "asset_type": instrument.get("assetType", ""),
                "cusip": instrument.get("cusip", ""),

                # 포지션 정보
                "quantity": position_data.get("longQuantity", 0.0),
                "average_price": position_data.get("averagePrice", 0.0),
                "market_value": position_data.get("marketValue", 0.0),
                "current_price": position_data.get("currentPrice", 0.0),

                # 손익 정보
                "day_gain_loss": position_data.get("currentDayProfitLoss", 0.0),
                "day_gain_loss_percent": position_data.get("currentDayProfitLossPercentage", 0.0),
                "total_gain_loss": self._calculate_total_pnl(
                    position_data.get("longQuantity", 0.0),
                    position_data.get("averagePrice", 0.0),
                    position_data.get("currentPrice", 0.0)
                ),

                "timestamp": datetime.now(timezone.utc)
            }

            # 총 손익 퍼센트 계산
            if position["average_price"] > 0:
                position["total_gain_loss_percent"] = (
                    (position["current_price"] - position["average_price"]) /
                    position["average_price"]
                ) * 100.0
            else:
                position["total_gain_loss_percent"] = 0.0

            return position

        except Exception as e:
            logger.error(f"Error processing position data: {e}")
            return None

    def _calculate_total_pnl(
        self,
        quantity: float,
        average_price: float,
        current_price: float
    ) -> float:
        """총 손익 계산"""
        return quantity * (current_price - average_price)

    async def get_cash_balance(self, account_hash: str) -> Dict[str, float]:
        """
        현금 잔고 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            현금 잔고 정보
        """
        try:
            logger.debug(f"Getting cash balance for {account_hash}")

            account_info = await self.schwab_service.get_account_info(account_hash)
            current_balances = account_info["securitiesAccount"]["currentBalances"]

            cash_info = {
                "cash_balance": current_balances.get("cashBalance", 0.0),
                "available_funds": current_balances.get("availableFunds", 0.0),
                "buying_power": current_balances.get("buyingPower", 0.0),
                "cash_receipts": current_balances.get("cashReceipts", 0.0),
                "pending_deposits": current_balances.get("pendingDeposits", 0.0),
                "timestamp": datetime.now(timezone.utc)
            }

            logger.debug(f"Cash balance retrieved: ${cash_info['cash_balance']:.2f}")
            return cash_info

        except Exception as e:
            logger.error(f"Failed to get cash balance: {e}")
            raise AccountException(f"Failed to get cash balance: {e}")

    async def get_buying_power(self, account_hash: str) -> float:
        """
        매수력 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            매수력
        """
        try:
            cash_info = await self.get_cash_balance(account_hash)
            return cash_info["buying_power"]

        except Exception as e:
            logger.error(f"Failed to get buying power: {e}")
            raise AccountException(f"Failed to get buying power: {e}")

    async def check_sufficient_funds(
        self,
        account_hash: str,
        required_amount: float
    ) -> Dict[str, Any]:
        """
        자금 충분성 확인

        Args:
            account_hash: 계좌 해시
            required_amount: 필요 금액

        Returns:
            자금 확인 결과
        """
        try:
            buying_power = await self.get_buying_power(account_hash)

            result = {
                "account_hash": account_hash,
                "required_amount": required_amount,
                "available_buying_power": buying_power,
                "sufficient_funds": buying_power >= required_amount,
                "shortfall": max(0, required_amount - buying_power),
                "timestamp": datetime.now(timezone.utc)
            }

            if result["sufficient_funds"]:
                logger.debug(
                    f"Sufficient funds available: ${buying_power:.2f} >= ${required_amount:.2f}"
                )
            else:
                logger.warning(
                    f"Insufficient funds: ${buying_power:.2f} < ${required_amount:.2f}, "
                    f"shortfall: ${result['shortfall']:.2f}"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to check funds: {e}")
            raise AccountException(f"Failed to check funds: {e}")

    async def get_portfolio_summary(self, account_hash: str) -> Dict[str, Any]:
        """
        포트폴리오 요약 정보

        Args:
            account_hash: 계좌 해시

        Returns:
            포트폴리오 요약
        """
        try:
            logger.debug(f"Getting portfolio summary for {account_hash}")

            # 계좌 요약과 포지션 정보를 병렬로 조회
            account_summary, positions = await asyncio.gather(
                self.get_account_summary(account_hash),
                self.get_positions(account_hash)
            )

            # 포지션 통계 계산
            total_positions = len(positions)
            profitable_positions = len([p for p in positions if p["total_gain_loss"] > 0])
            losing_positions = len([p for p in positions if p["total_gain_loss"] < 0])

            total_position_value = sum(p["market_value"] for p in positions)
            total_gain_loss = sum(p["total_gain_loss"] for p in positions)

            # 섹터별 분포 (간단한 예시)
            sector_allocation = self._calculate_sector_allocation(positions)

            portfolio_summary = {
                **account_summary,

                # 포지션 통계
                "total_positions": total_positions,
                "profitable_positions": profitable_positions,
                "losing_positions": losing_positions,
                "win_rate": profitable_positions / total_positions if total_positions > 0 else 0.0,

                # 가치 정보
                "total_position_value": total_position_value,
                "total_gain_loss": total_gain_loss,
                "total_gain_loss_percent": (
                    total_gain_loss / (total_position_value - total_gain_loss) * 100.0
                    if total_position_value - total_gain_loss > 0 else 0.0
                ),

                # 분산 정보
                "cash_percentage": (
                    account_summary["cash_balance"] / account_summary["total_value"] * 100.0
                    if account_summary["total_value"] > 0 else 0.0
                ),
                "equity_percentage": (
                    total_position_value / account_summary["total_value"] * 100.0
                    if account_summary["total_value"] > 0 else 0.0
                ),

                # 섹터 분포
                "sector_allocation": sector_allocation,

                # 포지션 목록
                "positions": positions
            }

            logger.debug(f"Portfolio summary generated with {total_positions} positions")
            return portfolio_summary

        except Exception as e:
            logger.error(f"Failed to get portfolio summary: {e}")
            raise AccountException(f"Failed to get portfolio summary: {e}")

    def _calculate_sector_allocation(self, positions: List[Dict[str, Any]]) -> Dict[str, float]:
        """섹터별 자산 분포 계산 (간단한 예시)"""
        # 실제 구현에서는 심볼별 섹터 정보를 조회해야 함
        # 여기서는 예시로 기본 분류만 제공

        total_value = sum(p["market_value"] for p in positions)
        if total_value == 0:
            return {}

        # 심볼 기반 간단한 섹터 분류 (예시)
        tech_symbols = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "META", "NFLX"}
        finance_symbols = {"JPM", "BAC", "WFC", "GS", "MS"}

        tech_value = sum(
            p["market_value"] for p in positions
            if p["symbol"] in tech_symbols
        )
        finance_value = sum(
            p["market_value"] for p in positions
            if p["symbol"] in finance_symbols
        )
        other_value = total_value - tech_value - finance_value

        return {
            "Technology": (tech_value / total_value) * 100.0,
            "Financials": (finance_value / total_value) * 100.0,
            "Other": (other_value / total_value) * 100.0
        }