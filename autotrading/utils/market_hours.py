"""
미국 주식 시장 시간 검증 모듈

NYSE/NASDAQ 정규 거래시간 및 거래일 확인 기능을 제공합니다.
"""

from datetime import datetime, time
from typing import Dict, Any, Optional
import pytz
import logging

logger = logging.getLogger(__name__)

# 미국 동부 시간대
US_EASTERN = pytz.timezone('US/Eastern')

# 정규 거래시간 (EST/EDT)
MARKET_OPEN_TIME = time(9, 30)  # 9:30 AM
MARKET_CLOSE_TIME = time(16, 0)  # 4:00 PM

# 주말 제외 (월요일=0, 일요일=6)
TRADING_WEEKDAYS = [0, 1, 2, 3, 4]  # 월-금


class MarketHoursValidator:
    """시장 시간 검증기"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.MarketHoursValidator")

    def get_current_eastern_time(self) -> datetime:
        """현재 시간을 미국 동부 시간으로 변환"""
        utc_now = datetime.now(pytz.utc)
        eastern_now = utc_now.astimezone(US_EASTERN)

        self.logger.debug(f"UTC: {utc_now}, Eastern: {eastern_now}")
        return eastern_now

    def is_trading_day(self, dt: Optional[datetime] = None) -> bool:
        """거래일 여부 확인 (주말 제외)"""
        if dt is None:
            dt = self.get_current_eastern_time()

        is_weekday = dt.weekday() in TRADING_WEEKDAYS

        self.logger.debug(f"Date: {dt.date()}, Weekday: {dt.weekday()}, Is trading day: {is_weekday}")
        return is_weekday

    def is_market_hours(self, dt: Optional[datetime] = None) -> bool:
        """정규 거래시간 여부 확인"""
        if dt is None:
            dt = self.get_current_eastern_time()

        current_time = dt.time()
        in_hours = MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME

        self.logger.debug(f"Time: {current_time}, Market hours: {MARKET_OPEN_TIME}-{MARKET_CLOSE_TIME}, In hours: {in_hours}")
        return in_hours

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """시장 개장 여부 확인 (거래일 + 거래시간)"""
        if dt is None:
            dt = self.get_current_eastern_time()

        trading_day = self.is_trading_day(dt)
        market_hours = self.is_market_hours(dt)
        is_open = trading_day and market_hours

        self.logger.info(f"Market status: Trading day: {trading_day}, Market hours: {market_hours}, Open: {is_open}")
        return is_open

    def get_market_status(self) -> Dict[str, Any]:
        """현재 시장 상태 종합 정보"""
        eastern_time = self.get_current_eastern_time()

        status = {
            'current_time_eastern': eastern_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'current_date': eastern_time.date().isoformat(),
            'current_time': eastern_time.time().isoformat(),
            'weekday': eastern_time.weekday(),
            'weekday_name': eastern_time.strftime('%A'),
            'is_trading_day': self.is_trading_day(eastern_time),
            'is_market_hours': self.is_market_hours(eastern_time),
            'is_market_open': self.is_market_open(eastern_time),
            'market_open_time': MARKET_OPEN_TIME.isoformat(),
            'market_close_time': MARKET_CLOSE_TIME.isoformat(),
            'timezone': 'US/Eastern'
        }

        # 시장 상태 메시지
        if status['is_market_open']:
            status['message'] = '시장이 열려있습니다'
            status['status'] = 'OPEN'
        elif not status['is_trading_day']:
            status['message'] = f"거래일이 아닙니다 ({status['weekday_name']})"
            status['status'] = 'CLOSED_WEEKEND'
        elif not status['is_market_hours']:
            status['message'] = f"거래시간이 아닙니다 (현재: {status['current_time']}, 거래시간: {status['market_open_time']}-{status['market_close_time']})"
            status['status'] = 'CLOSED_HOURS'
        else:
            status['message'] = '시장이 닫혀있습니다'
            status['status'] = 'CLOSED'

        return status

    def wait_for_market_open(self, max_wait_minutes: int = 60) -> bool:
        """시장 개장까지 대기 (최대 대기시간 제한)"""
        eastern_time = self.get_current_eastern_time()

        if self.is_market_open(eastern_time):
            self.logger.info("시장이 이미 열려있습니다")
            return True

        # 간단한 구현: 시장이 닫혀있으면 False 반환
        # 실제 구현에서는 다음 개장시간까지 계산 가능
        status = self.get_market_status()
        self.logger.warning(f"시장이 닫혀있습니다: {status['message']}")
        return False


def check_market_status() -> Dict[str, Any]:
    """시장 상태 확인 함수 (편의 함수)"""
    validator = MarketHoursValidator()
    return validator.get_market_status()


def is_market_open_now() -> bool:
    """현재 시장 개장 여부 확인 (편의 함수)"""
    validator = MarketHoursValidator()
    return validator.is_market_open()