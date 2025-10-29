"""Trading calendar utilities for multi-market trading."""
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Optional, Set, Tuple

try:
    from zoneinfo import ZoneInfo

    has_zoneinfo = True
except ImportError:  # pragma: no cover - Python <3.9 fallback
    has_zoneinfo = False
    ZoneInfo = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import akshare as ak  # type: ignore
except ImportError:
    ak = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import pandas as pd  # type: ignore
except ImportError:
    pd = None  # type: ignore


MORNING_OPEN = dt_time(9, 30)
MORNING_CLOSE = dt_time(11, 30)
AFTERNOON_OPEN = dt_time(13, 0)
AFTERNOON_CLOSE = dt_time(15, 0)

A_SHARE_DEFAULT_HOLIDAYS = {
    date(2024, 1, 1),
    date(2024, 2, 9),
    date(2024, 2, 12),
    date(2024, 2, 13),
    date(2024, 2, 14),
    date(2024, 2, 15),
    date(2024, 2, 16),
    date(2024, 2, 19),
    date(2024, 4, 4),
    date(2024, 4, 5),
    date(2024, 5, 1),
    date(2024, 5, 2),
    date(2024, 5, 3),
    date(2024, 6, 10),
    date(2024, 9, 16),
    date(2024, 9, 17),
    date(2024, 10, 1),
    date(2024, 10, 2),
    date(2024, 10, 3),
    date(2024, 10, 4),
    date(2024, 10, 7),
    date(2025, 1, 1),
    date(2025, 1, 27),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 1, 31),
    date(2025, 4, 4),
    date(2025, 5, 1),
    date(2025, 5, 2),
    date(2025, 10, 1),
    date(2025, 10, 2),
    date(2025, 10, 3),
    date(2025, 10, 6),
    date(2025, 10, 7),
}

A_SHARE_COMPENSATORY_WORKDAYS = {
    date(2024, 2, 18),
    date(2024, 4, 7),
    date(2024, 4, 28),
    date(2024, 5, 11),
    date(2024, 9, 14),
    date(2024, 9, 29),
    date(2024, 10, 12),
    date(2025, 1, 26),
    date(2025, 2, 8),
    date(2025, 4, 27),
    date(2025, 9, 28),
    date(2025, 10, 11),
}

if has_zoneinfo:
    CN_TZ = ZoneInfo("Asia/Shanghai")
    UTC_TZ = ZoneInfo("UTC")
else:  # pragma: no cover - fallback for environments without zoneinfo
    CN_TZ = timezone(timedelta(hours=8))
    UTC_TZ = timezone.utc


class MarketCalendar:
    """Provide trading session awareness for supported markets."""

    def __init__(self) -> None:
        self.cn_tz = CN_TZ
        self._calendar_cache: Optional[Tuple[date, Set[date]]] = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def is_market_open(self, market_type: str, when: Optional[datetime] = None) -> bool:
        status = self.get_market_status(market_type, when)
        return status.get("market_open", False)

    def get_market_status(self, market_type: str, when: Optional[datetime] = None) -> dict:
        market_key = (market_type or "crypto").lower()
        if market_key == "a_share":
            return self._get_a_share_status(when)
        now = self._ensure_utc(when)
        return {
            "market_type": "crypto",
            "market_open": True,
            "current_session": "continuous",
            "is_holiday": False,
            "reason": None,
            "server_time": now.isoformat().replace("+00:00", "Z"),
            "next_open": None,
        }

    def next_trading_day(self, market_type: str, from_date: date) -> date:
        market_key = (market_type or "crypto").lower()
        if market_key != "a_share":
            return from_date + timedelta(days=1)

        current = from_date
        while True:
            current += timedelta(days=1)
            if self._is_a_share_trading_day(current):
                return current

    def next_sellable_date(self, market_type: str, trade_datetime: Optional[datetime]) -> Optional[str]:
        if trade_datetime is None:
            return None
        market_key = (market_type or "crypto").lower()
        if market_key != "a_share":
            return trade_datetime.date().isoformat()

        localized = self._ensure_cn(trade_datetime)
        next_day = self.next_trading_day("a_share", localized.date())
        return next_day.isoformat()

    def is_trading_day(self, market_type: str, check_date: Optional[date] = None) -> bool:
        market_key = (market_type or "crypto").lower()
        probe_date = check_date or datetime.now(self.cn_tz).date()
        if market_key != "a_share":
            return True
        return self._is_a_share_trading_day(probe_date)

    def is_trading_session_now(self, market_type: str, when: Optional[datetime] = None) -> bool:
        market_key = (market_type or "crypto").lower()
        if market_key != "a_share":
            return True
        status = self._get_a_share_status(when)
        return status.get("market_open", False)

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------
    def _get_a_share_status(self, when: Optional[datetime]) -> dict:
        now_cn = self._ensure_cn(when)
        today = now_cn.date()
        time_now = now_cn.time()

        is_trading_day = self._is_a_share_trading_day(today)
        session = None
        market_open = False
        reason = None

        if not is_trading_day:
            reason = "Weekend" if today.weekday() >= 5 else "Holiday"
        else:
            if MORNING_OPEN <= time_now < MORNING_CLOSE:
                session = "morning"
                market_open = True
            elif AFTERNOON_OPEN <= time_now < AFTERNOON_CLOSE:
                session = "afternoon"
                market_open = True
            elif time_now < MORNING_OPEN:
                reason = "Pre-market"
            elif MORNING_CLOSE <= time_now < AFTERNOON_OPEN:
                reason = "Midday break"
            else:
                reason = "Post-market"

        next_open_dt = None if market_open else self._next_a_share_open_datetime(now_cn)

        return {
            "market_type": "a_share",
            "market_open": market_open,
            "current_session": session,
            "is_holiday": not is_trading_day,
            "reason": reason,
            "server_time": now_cn.isoformat(),
            "next_open": next_open_dt.isoformat() if next_open_dt else None,
        }

    def _next_a_share_open_datetime(self, now_cn: datetime) -> datetime:
        today = now_cn.date()
        time_now = now_cn.time()

        if self._is_a_share_trading_day(today):
            if time_now < MORNING_OPEN:
                return datetime.combine(today, MORNING_OPEN, tzinfo=self.cn_tz)
            if MORNING_CLOSE <= time_now < AFTERNOON_OPEN:
                return datetime.combine(today, AFTERNOON_OPEN, tzinfo=self.cn_tz)

        next_day = today
        while True:
            next_day += timedelta(days=1)
            if self._is_a_share_trading_day(next_day):
                return datetime.combine(next_day, MORNING_OPEN, tzinfo=self.cn_tz)

    # ------------------------------------------------------------------
    # Calendar helpers
    # ------------------------------------------------------------------
    def _ensure_calendar(self) -> Set[date]:
        today = datetime.now(self.cn_tz).date()
        if self._calendar_cache:
            cached_day, cached_calendar = self._calendar_cache
            if cached_day == today:
                return cached_calendar

        calendar_days: Set[date] = set()
        if ak is not None:
            try:
                df = ak.tool_trade_date_hist_sina()  # type: ignore[attr-defined]
                if pd is not None and isinstance(df, pd.DataFrame) and not df.empty:
                    for value in df.iloc[:, 0].tolist():
                        try:
                            calendar_days.add(pd.to_datetime(value).date())
                        except Exception:  # pragma: no cover - defensive
                            calendar_days.add(_coerce_to_date(value))
                elif isinstance(df, list):  # pragma: no cover - defensive
                    for value in df:
                        calendar_days.add(_coerce_to_date(value))
            except Exception as exc:  # pragma: no cover - network failures
                print(f"[WARN] Failed to refresh A-share trading calendar: {exc}")

        if not calendar_days:
            calendar_days = self._fallback_calendar(today)

        self._calendar_cache = (today, calendar_days)
        return calendar_days

    def _fallback_calendar(self, today: date) -> Set[date]:
        start = today - timedelta(days=365)
        end = today + timedelta(days=365)
        days: Set[date] = set()
        for offset in range((end - start).days + 1):
            current = start + timedelta(days=offset)
            if current in A_SHARE_COMPENSATORY_WORKDAYS:
                days.add(current)
                continue
            if current.weekday() >= 5:
                continue
            if current in A_SHARE_DEFAULT_HOLIDAYS:
                continue
            days.add(current)
        return days

    def _is_a_share_trading_day(self, check_date: date) -> bool:
        calendar_days = self._ensure_calendar()
        if check_date in calendar_days:
            return True
        if check_date in A_SHARE_COMPENSATORY_WORKDAYS:
            return True
        if check_date in A_SHARE_DEFAULT_HOLIDAYS:
            return False
        return check_date.weekday() < 5

    # ------------------------------------------------------------------
    # Timezone helpers
    # ------------------------------------------------------------------
    def _ensure_cn(self, when: Optional[datetime]) -> datetime:
        if when is None:
            return datetime.now(self.cn_tz)
        if when.tzinfo is None:
            return when.replace(tzinfo=self.cn_tz)
        return when.astimezone(self.cn_tz)

    def _ensure_utc(self, when: Optional[datetime]) -> datetime:
        if when is None:
            return datetime.utcnow().replace(tzinfo=UTC_TZ)
        if when.tzinfo is None:
            return when.replace(tzinfo=UTC_TZ)
        return when.astimezone(UTC_TZ)


def _coerce_to_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value.split(" ")[0], "%Y-%m-%d").date()
        except ValueError:
            pass
    # Fallback to today's date when parsing fails; this keeps calendar usable.
    return datetime.now(CN_TZ).date()
