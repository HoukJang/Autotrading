"""
Market Data Service

시장 데이터 수집 및 처리를 담당하는 서비스입니다.
DataCollector 컴포넌트에서 사용됩니다.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging

import pandas as pd
import numpy as np

from .schwab_service import SchwabAPIService, SchwabAPIException

logger = logging.getLogger(__name__)


class MarketDataException(Exception):
    """시장 데이터 관련 예외"""
    pass


class MarketDataService:
    """
    시장 데이터 서비스

    Schwab API를 통해 시장 데이터를 수집하고 검증하는 서비스입니다.
    DataCollector에서 사용되며 다음 기능을 제공합니다:
    - 실시간 시세 데이터 수집
    - 히스토리컬 OHLCV 데이터 수집
    - 데이터 검증 및 정제
    - UTC 시간 표준화
    """

    def __init__(self, schwab_service: SchwabAPIService):
        """
        Market Data Service 초기화

        Args:
            schwab_service: Schwab API 서비스 인스턴스
        """
        self.schwab_service = schwab_service
        self.logger = logging.getLogger(__name__)

    async def get_latest_bars(
        self,
        symbols: List[str],
        period_days: int = 1
    ) -> Dict[str, pd.DataFrame]:
        """
        최신 분봉 데이터 수집

        Args:
            symbols: 수집할 심볼 목록
            period_days: 수집할 기간 (일)

        Returns:
            심볼별 OHLCV 데이터프레임 딕셔너리
        """
        logger.info(f"Collecting latest bars for {len(symbols)} symbols, {period_days} days")

        results = {}
        failed_symbols = []

        # 병렬로 데이터 수집
        tasks = [
            self._get_symbol_bars(symbol, period_days)
            for symbol in symbols
        ]

        symbol_results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, result in zip(symbols, symbol_results):
            if isinstance(result, Exception):
                logger.error(f"Failed to collect data for {symbol}: {result}")
                failed_symbols.append(symbol)
                continue

            if result is not None and not result.empty:
                results[symbol] = result
                logger.debug(f"Collected {len(result)} bars for {symbol}")
            else:
                logger.warning(f"No data returned for {symbol}")
                failed_symbols.append(symbol)

        if failed_symbols:
            logger.warning(f"Failed to collect data for symbols: {failed_symbols}")

        logger.info(f"Successfully collected data for {len(results)}/{len(symbols)} symbols")
        return results

    async def _get_symbol_bars(
        self,
        symbol: str,
        period_days: int
    ) -> Optional[pd.DataFrame]:
        """
        개별 심볼의 분봉 데이터 수집

        Args:
            symbol: 심볼
            period_days: 수집 기간 (일)

        Returns:
            OHLCV 데이터프레임 또는 None
        """
        try:
            # Schwab API로 데이터 수집
            market_data = await self.schwab_service.get_market_data(
                symbols=symbol,
                period_type="day",
                period=period_days,
                frequency_type="minute",
                frequency=1
            )

            if symbol not in market_data or "error" in market_data[symbol]:
                error_msg = market_data[symbol].get("error", "Unknown error")
                raise MarketDataException(f"API error for {symbol}: {error_msg}")

            # 데이터 파싱 및 변환
            df = self._parse_schwab_data(market_data[symbol], symbol)

            if df is None or df.empty:
                logger.warning(f"No valid data parsed for {symbol}")
                return None

            # 데이터 검증
            validated_df = self.validate_minute_bars(df)

            return validated_df

        except Exception as e:
            logger.error(f"Error collecting data for {symbol}: {e}")
            raise MarketDataException(f"Failed to collect data for {symbol}: {e}")

    def _parse_schwab_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[pd.DataFrame]:
        """
        Schwab API 응답 데이터를 DataFrame으로 변환

        Args:
            raw_data: Schwab API 응답 데이터
            symbol: 심볼

        Returns:
            OHLCV 데이터프레임
        """
        try:
            if "candles" not in raw_data:
                logger.warning(f"No candles data found for {symbol}")
                return None

            candles = raw_data["candles"]
            if not candles:
                logger.warning(f"Empty candles data for {symbol}")
                return None

            # DataFrame 생성
            df = pd.DataFrame(candles)

            # 필수 컬럼 확인
            required_columns = ["datetime", "open", "high", "low", "close", "volume"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                raise MarketDataException(f"Missing columns for {symbol}: {missing_columns}")

            # 타임스탬프 변환
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)

            # 컬럼명 표준화
            df = df.rename(columns={
                "datetime": "ts",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume"
            })

            # 심볼 컬럼 추가
            df["symbol"] = symbol
            df["source"] = "schwab"

            # 컬럼 순서 정리
            df = df[["symbol", "ts", "open", "high", "low", "close", "volume", "source"]]

            # 시간순 정렬
            df = df.sort_values("ts").reset_index(drop=True)

            logger.debug(f"Parsed {len(df)} bars for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error parsing data for {symbol}: {e}")
            return None

    def validate_minute_bars(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        분봉 데이터 검증 및 정제

        Args:
            df: 검증할 데이터프레임

        Returns:
            검증된 데이터프레임

        Raises:
            MarketDataException: 데이터 검증 실패
        """
        if df is None or df.empty:
            raise MarketDataException("Empty dataframe provided for validation")

        original_length = len(df)
        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else "unknown"

        try:
            # 1. 타임스탬프 검증 (UTC, 1분 단위)
            df = self._validate_timestamps(df)

            # 2. OHLCV 데이터 검증
            df = self._validate_ohlcv_data(df)

            # 3. 중복 제거
            df = df.drop_duplicates(subset=["symbol", "ts"]).reset_index(drop=True)

            # 4. 정렬
            df = df.sort_values(["symbol", "ts"]).reset_index(drop=True)

            validated_length = len(df)
            removed_count = original_length - validated_length

            if removed_count > 0:
                logger.info(
                    f"Validation removed {removed_count}/{original_length} invalid bars "
                    f"for {symbol}"
                )

            if validated_length == 0:
                raise MarketDataException(f"All bars invalid for {symbol}")

            logger.debug(f"Validation passed for {symbol}: {validated_length} valid bars")
            return df

        except Exception as e:
            logger.error(f"Validation failed for {symbol}: {e}")
            raise MarketDataException(f"Validation failed for {symbol}: {e}")

    def _validate_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """타임스탬프 검증"""
        # UTC 변환 확인
        if df["ts"].dt.tz is None:
            df["ts"] = df["ts"].dt.tz_localize("UTC")
        elif str(df["ts"].dt.tz) != "UTC":
            df["ts"] = df["ts"].dt.tz_convert("UTC")

        # 1분 단위로 정규화
        df["ts"] = df["ts"].dt.floor("T")

        # 유효하지 않은 타임스탬프 제거
        df = df.dropna(subset=["ts"])

        return df

    def _validate_ohlcv_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """OHLCV 데이터 검증"""
        # 숫자 컬럼 변환
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # NaN, 무한대, 음수 볼륨 제거
        df = df.dropna(subset=numeric_columns)
        df = df[~df[numeric_columns].isin([np.inf, -np.inf]).any(axis=1)]
        df = df[df["volume"] >= 0]

        # OHLC 논리 검증 (High >= Open,Close,Low, Low <= Open,Close,High)
        valid_ohlc = (
            (df["high"] >= df["open"]) &
            (df["high"] >= df["close"]) &
            (df["high"] >= df["low"]) &
            (df["low"] <= df["open"]) &
            (df["low"] <= df["close"]) &
            (df["low"] <= df["high"])
        )

        df = df[valid_ohlc]

        return df

    async def get_real_time_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        실시간 시세 조회

        Args:
            symbols: 조회할 심볼 목록

        Returns:
            심볼별 실시간 시세 데이터
        """
        try:
            logger.debug(f"Getting real-time quotes for {len(symbols)} symbols")

            quotes_data = await self.schwab_service.get_quotes(symbols)

            if not quotes_data:
                logger.warning("No quotes data received")
                return {}

            # 데이터 정제 및 표준화
            processed_quotes = {}
            for symbol, quote in quotes_data.items():
                if isinstance(quote, dict) and "error" not in quote:
                    processed_quotes[symbol] = self._process_quote_data(quote, symbol)
                else:
                    logger.warning(f"Invalid quote data for {symbol}: {quote}")

            logger.debug(f"Successfully processed {len(processed_quotes)} quotes")
            return processed_quotes

        except Exception as e:
            logger.error(f"Error getting real-time quotes: {e}")
            raise MarketDataException(f"Failed to get real-time quotes: {e}")

    def _process_quote_data(self, quote: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """실시간 시세 데이터 처리"""
        try:
            processed = {
                "symbol": symbol,
                "last_price": quote.get("lastPrice", 0.0),
                "bid_price": quote.get("bidPrice", 0.0),
                "ask_price": quote.get("askPrice", 0.0),
                "bid_size": quote.get("bidSize", 0),
                "ask_size": quote.get("askSize", 0),
                "volume": quote.get("totalVolume", 0),
                "timestamp": datetime.now(timezone.utc),
                "market_time": quote.get("quoteTimeInLong"),
                "source": "schwab"
            }

            # 타임스탬프 변환
            if processed["market_time"]:
                processed["market_time"] = pd.to_datetime(
                    processed["market_time"], unit="ms", utc=True
                )

            return processed

        except Exception as e:
            logger.error(f"Error processing quote data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    async def get_historical_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: Optional[datetime] = None,
        frequency: str = "1min"
    ) -> Dict[str, pd.DataFrame]:
        """
        히스토리컬 데이터 수집

        Args:
            symbols: 심볼 목록
            start_date: 시작 날짜
            end_date: 종료 날짜 (None이면 현재)
            frequency: 데이터 빈도 (1min, 5min, 15min, 1hour, 1day)

        Returns:
            심볼별 히스토리컬 데이터
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        period_days = (end_date - start_date).days
        if period_days <= 0:
            raise MarketDataException("Invalid date range")

        logger.info(
            f"Collecting historical data for {len(symbols)} symbols, "
            f"{period_days} days, frequency: {frequency}"
        )

        # 빈도별 설정
        freq_mapping = {
            "1min": (1, "minute"),
            "5min": (5, "minute"),
            "15min": (15, "minute"),
            "30min": (30, "minute"),
            "1hour": (1, "minute"),  # Schwab API는 분봉으로만 제공
            "1day": (1, "daily")
        }

        if frequency not in freq_mapping:
            raise MarketDataException(f"Unsupported frequency: {frequency}")

        freq_value, freq_type = freq_mapping[frequency]

        results = {}
        for symbol in symbols:
            try:
                market_data = await self.schwab_service.get_market_data(
                    symbols=symbol,
                    period_type="day",
                    period=min(period_days, 20),  # API 제한
                    frequency_type=freq_type,
                    frequency=freq_value
                )

                if symbol in market_data and "error" not in market_data[symbol]:
                    df = self._parse_schwab_data(market_data[symbol], symbol)
                    if df is not None and not df.empty:
                        # 날짜 범위 필터링
                        mask = (df["ts"] >= start_date) & (df["ts"] <= end_date)
                        df = df[mask]

                        results[symbol] = self.validate_minute_bars(df)

            except Exception as e:
                logger.error(f"Error collecting historical data for {symbol}: {e}")

        logger.info(f"Historical data collection completed for {len(results)} symbols")
        return results