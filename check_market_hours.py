"""
Check current market hours for ES futures
"""
from datetime import datetime, timezone
import pytz

# 시카고 시간대
chicago_tz = pytz.timezone('America/Chicago')

# 현재 시간
now_utc = datetime.now(timezone.utc)
now_chicago = now_utc.astimezone(chicago_tz)
now_korea = now_utc.astimezone(pytz.timezone('Asia/Seoul'))

print("=" * 70)
print("Current Time Check")
print("=" * 70)
print(f"Korea Time (KST):    {now_korea.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"Chicago Time (CT):   {now_chicago.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"UTC:                 {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print()

# 요일 확인
weekday = now_chicago.weekday()  # 0=월, 6=일
hour = now_chicago.hour
minute = now_chicago.minute

print("=" * 70)
print("ES Futures Market Hours (Chicago Time)")
print("=" * 70)
print("Trading Hours:")
print("  - Sunday    17:00 ~ Monday    16:00")
print("  - Monday    17:00 ~ Tuesday   16:00")
print("  - Tuesday   17:00 ~ Wednesday 16:00")
print("  - Wednesday 17:00 ~ Thursday  16:00")
print("  - Thursday  17:00 ~ Friday    16:00")
print("  - Break: Daily 16:00-17:00 (1 hour)")
print()

# 시장 상태 판단
is_open = False

if weekday == 6:  # 일요일
    if hour >= 17:  # 17:00 이후
        is_open = True
elif weekday == 4:  # 금요일
    if hour < 16:  # 16:00 이전
        is_open = True
    elif hour == 16 and minute == 0:
        is_open = False  # 정확히 16:00은 마감
elif weekday in [0, 1, 2, 3]:  # 월~목
    # 16:00-17:00 휴식 제외
    if hour == 16:
        is_open = False
    else:
        is_open = True

print("=" * 70)
print("Market Status")
print("=" * 70)
if is_open:
    print("✅ MARKET IS OPEN")
    print("   → You can test real-time data collection")
else:
    print("❌ MARKET IS CLOSED")

    # 다음 개장 시간 계산
    if weekday == 6 and hour < 17:  # 일요일 17시 전
        hours_until_open = 17 - hour - 1 + (60 - minute) / 60
        print(f"   → Market opens in {hours_until_open:.1f} hours (Sunday 17:00 CT)")
    elif weekday == 4 and hour >= 16:  # 금요일 16시 이후
        days_until_sunday = 2
        hours_until_sunday = (days_until_sunday * 24) + (17 - hour) - 1 + (60 - minute) / 60
        print(f"   → Market opens in {hours_until_sunday:.1f} hours (Sunday 17:00 CT)")
    elif weekday == 5:  # 토요일
        days_until_sunday = 1
        hours_until_sunday = (days_until_sunday * 24) + (17 - hour) - 1 + (60 - minute) / 60
        print(f"   → Market opens in {hours_until_sunday:.1f} hours (Sunday 17:00 CT)")
    elif hour == 16:  # 매일 휴식 시간
        print(f"   → Market opens in {60 - minute} minutes (17:00 CT)")

    print("   → Historical data testing is still available")

print("=" * 70)
