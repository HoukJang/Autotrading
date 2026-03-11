"""Single Source of Truth for all trading constants.

Every trading parameter used by both the live system and the backtester
is defined here exactly once.  Individual modules import from this file
instead of defining their own copies.

Backtest-only constants (SLIPPAGE_BPS, COMMISSION_PER_SHARE, CASH_YIELD,
etc.) remain in batch_simulator.py since they have no live-system equivalent.

Section layout:
    1. Position limits & portfolio heat
    2. Per-strategy position caps
    3. Daily entry limits
    4. Risk per trade
    5. GDR (Graduated Drawdown Response) -- per-strategy
    6. GDR -- legacy portfolio-level (backward compat)
    7. Portfolio Safety Net
    8. Exit rules: SL / TP / Trailing / Emergency / Time
    9. 2-stage SL upgrade
   10. Allocation engine sizing
   11. Gap filter
   12. Scanner / warmup
   13. Strategy names & groups
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Position limits & portfolio heat
# ---------------------------------------------------------------------------

MAX_LONG_POSITIONS: int = 8             # Iter 29: increased from 6
MAX_SHORT_POSITIONS: int = 3
MAX_TOTAL_POSITIONS: int = 9            # overall position cap
MAX_PORTFOLIO_HEAT_PCT: float = 0.90    # max 90% of equity exposed (Panel #37)

# ---------------------------------------------------------------------------
# 2. Per-strategy position caps
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
# ---------------------------------------------------------------------------

MAX_STRATEGY_POSITIONS: dict[str, int] = {
    "breakout_momentum": 2,              # BM: max 2 concurrent (LOCKED)
    "rsi_mean_reversion": 4,             # MR: max 4 concurrent (Panel #31)
}
DEFAULT_STRATEGY_CAP: int = 2            # fallback for unknown strategies

# Soft per-strategy cap (same values, used by batch_simulator when
# 2+ strategies have pending signals on the same day)
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
SOFT_STRATEGY_CAP: dict[str, int] = {
    "breakout_momentum": 2,              # LOCKED (Iter 30 confirmed cap 3 worse)
    "rsi_mean_reversion": 4,             # Panel #31: expanded from 3
}

# ---------------------------------------------------------------------------
# 3. Daily entry limits
# ---------------------------------------------------------------------------

MAX_DAILY_ENTRIES: int = 3               # portfolio-level total cap (Iter 29)

# ---------------------------------------------------------------------------
# 4. Risk per trade
# ---------------------------------------------------------------------------

RISK_PER_TRADE_PCT: float = 0.02         # 2% of equity at risk per trade
MAX_LOSS_PER_TRADE_PCT: float = 0.03     # hard cap: max 3% of equity loss per trade

# Per-strategy base risk (overridden by regime allocation table)
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
STRATEGY_BASE_RISK: dict[str, float] = {
    "breakout_momentum": 0.020,          # 2.0%
    "rsi_mean_reversion": 0.015,         # 1.5%
}
DEFAULT_BASE_RISK: float = 0.02          # fallback for unknown strategies

# ---------------------------------------------------------------------------
# 5. GDR -- per-strategy thresholds & multipliers
# ---------------------------------------------------------------------------

PER_STRATEGY_GDR: bool = True            # True = per-strategy, False = portfolio-level

# Per-strategy GDR thresholds: (tier1_dd, tier2_dd)
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
STRATEGY_GDR_THRESHOLDS: dict[str, tuple[float, float]] = {
    "breakout_momentum": (0.04, 0.08),   # Tier1: 4% DD, Tier2: 8% DD (HALTED)
    "rsi_mean_reversion": (0.02, 0.04),  # Tier1: 2% DD, Tier2: 4% DD (HALTED)
}

# Risk multiplier per tier
GDR_RISK_MULT: dict[int, float] = {
    0: 1.0,    # normal
    1: 0.5,    # reduced
    2: 0.0,    # HALTED (no entries)
}

# Entry limit per strategy per day (by tier)
GDR_STRATEGY_ENTRIES: dict[int, int] = {
    0: 1,   # 1 entry per strategy per day
    1: 1,
    2: 0,   # halted
}

# ---------------------------------------------------------------------------
# 6. GDR -- legacy portfolio-level (backward compat)
# ---------------------------------------------------------------------------

GDR_ROLLING_WINDOW: int = 60            # rolling peak lookback (trading days)
GDR_TIER1_DD: float = 0.15              # DD > 15% -> Tier 1 (legacy)
GDR_TIER2_DD: float = 0.25              # DD > 25% -> Tier 2 (legacy)

GDR_LEGACY_RISK_MULT: dict[int, float] = {
    0: 1.0,    # Tier 0: normal
    1: 0.5,    # Tier 1: reduced
    2: 0.25,   # Tier 2: minimal
}

GDR_MAX_ENTRIES: dict[int, int] = {
    0: 2,   # Tier 0: 2 entries/day
    1: 1,   # Tier 1: 1 entry/day
    2: 1,   # Tier 2: 1 entry/day
}

# ---------------------------------------------------------------------------
# 7. Portfolio Safety Net
# ---------------------------------------------------------------------------

PORTFOLIO_SAFETY_NET_DD: float = 0.12          # activate at 12% total DD
PORTFOLIO_SAFETY_NET_RECOVERY: float = 0.08    # deactivate when DD < 8%
PORTFOLIO_SAFETY_NET_ENTRIES: int = 1           # 1 entry total when active
PORTFOLIO_SAFETY_NET_RISK: float = 0.005        # 0.5% risk when active

# ---------------------------------------------------------------------------
# 8. Exit rules: SL / TP / Trailing / Emergency / Time
# ---------------------------------------------------------------------------

# Emergency exit thresholds (Day 1 only)
EMERGENCY_LOSS_CONFIRM_PCT: float = 0.07     # -7%: need 2 consecutive bars
EMERGENCY_LOSS_IMMEDIATE_PCT: float = 0.10   # -10%: immediate single-bar exit
EMERGENCY_BARS_NEEDED: int = 2               # bars at -7% before triggering

# Strategy-specific SL ATR multipliers (by direction)
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
SL_ATR_MULT: dict[str, dict[str, float]] = {
    "rsi_mean_reversion": {"long": 1.5, "short": 0.75},
    "consecutive_down": {"long": 2.0},
    "ema_cross_trend": {"long": 3.0, "short": 3.0},
    "breakout_momentum": {"long": 2.5},
    "adaptive_mean_reversion": {"long": 2.5, "short": 2.0},
}

# Strategy-specific TP ATR multipliers (None = use indicator-based TP)
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
TP_ATR_MULT: dict[str, float | None] = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
    "ema_cross_trend": 5.0,
    "breakout_momentum": 4.0,
    "adaptive_mean_reversion": None,
}

# Strategy-specific max hold days
# SSOT: values here must match strategy/registry.py StrategyMeta declarations
MAX_HOLD_DAYS: dict[str, int] = {
    "breakout_momentum": 15,             # 3 weeks max for momentum strategy
    "rsi_mean_reversion": 5,
    "consecutive_down": 5,
    "ema_cross_trend": 10,
    "adaptive_mean_reversion": 7,
}

# Trailing stop configuration
TRAILING_STRATEGIES: frozenset[str] = frozenset({"ema_cross_trend", "breakout_momentum"})
TRAILING_ATR_MULT: float = 2.0

# Per-strategy trailing stop activation thresholds (ATR multiples)
TRAILING_ACTIVATION_ATR: dict[str, float] = {
    "ema_cross_trend": 1.5,
    "breakout_momentum": 1.5,      # reverted from 1.0 (Iter 25)
}

# --- Indicator-Based TP Constants ---
MR_AUXILIARY_TP_ATR_MULT: float = 2.0       # MR auxiliary ATR cap
ADAPTIVE_MR_TP_ATR_LONG: float = 2.5        # adaptive_mean_reversion long TP
ADAPTIVE_MR_TP_ATR_SHORT: float = 2.0       # adaptive_mean_reversion short TP

# ---------------------------------------------------------------------------
# 9. 2-stage SL upgrade
# ---------------------------------------------------------------------------

STAGE1_BE_ACTIVATION_ATR: float = 1.5     # Stage 1: move SL to breakeven
STAGE2_PROFIT_ACTIVATION_ATR: float = 1.2 # Stage 2: lock in profit
STAGE2_PROFIT_LOCK_ATR: float = 0.4       # SL moved to entry + this (Iter 26)

# ---------------------------------------------------------------------------
# 10. Allocation engine sizing
# ---------------------------------------------------------------------------

SHORT_SIZE_RATIO: float = 0.65            # Short positions sized at 65% of long
MAX_POSITION_PCT: float = 0.25            # Max 25% of equity per position (Iter 29)
MIN_POSITION_VALUE: float = 200.0         # Minimum $200 per position

# ---------------------------------------------------------------------------
# 11. Gap filter & entry order limits
# ---------------------------------------------------------------------------

DEFAULT_GAP_THRESHOLD: float = 0.03       # 3% max absolute gap fraction

# Limit order price cap: entry limit = prev_close * (1 +/- GAP_THRESHOLD)
# Long: prev_close * (1 + 0.03), Short: prev_close * (1 - 0.03)
# Orders not filled within LIMIT_ORDER_CANCEL_MINUTES are auto-cancelled.
LIMIT_ORDER_CANCEL_MINUTES: int = 30      # cancel unfilled entries 30 min after open

# ---------------------------------------------------------------------------
# 12. Scanner / warmup
# ---------------------------------------------------------------------------

MIN_BARS_WARMUP: int = 60                 # min bars before signal generation
WARMUP_PRELOAD_BARS: int = 80             # pre-loaded bars for indicator warmup

# ---------------------------------------------------------------------------
# 13. Strategy names & groups
# ---------------------------------------------------------------------------

STRATEGY_NAMES: list[str] = ["breakout_momentum", "rsi_mean_reversion"]

GROUP_A_STRATEGIES: frozenset[str] = frozenset({"breakout_momentum", "rsi_mean_reversion"})
GROUP_B_STRATEGIES: frozenset[str] = frozenset()

# Confirmation window gap tolerance (3 bps)
GAP_TOLERANCE: float = 0.003


# ---------------------------------------------------------------------------
# 14. Registry sync validation
# ---------------------------------------------------------------------------


def validate_registry_sync() -> list[str]:
    """Validate that StrategyMetaRegistry declarations match SSOT constants.

    Returns a list of mismatch descriptions.  An empty list means all
    registered strategies are in sync with the constants defined above.

    This function performs a lazy import of the strategy modules to
    ensure their self-registration code has executed before validation.
    """
    # Lazy import: trigger strategy module loading so self-registration runs
    import autotrader.strategy.breakout_momentum  # noqa: F401
    import autotrader.strategy.rsi_mean_reversion  # noqa: F401
    from autotrader.strategy.registry import StrategyMetaRegistry

    errors: list[str] = []

    for name, meta in StrategyMetaRegistry.all_strategies().items():
        # MAX_STRATEGY_POSITIONS
        if name in MAX_STRATEGY_POSITIONS:
            if MAX_STRATEGY_POSITIONS[name] != meta.max_positions:
                errors.append(
                    f"{name}: MAX_STRATEGY_POSITIONS={MAX_STRATEGY_POSITIONS[name]} "
                    f"!= meta.max_positions={meta.max_positions}"
                )

        # SOFT_STRATEGY_CAP
        if name in SOFT_STRATEGY_CAP:
            if SOFT_STRATEGY_CAP[name] != meta.soft_cap:
                errors.append(
                    f"{name}: SOFT_STRATEGY_CAP={SOFT_STRATEGY_CAP[name]} "
                    f"!= meta.soft_cap={meta.soft_cap}"
                )

        # STRATEGY_BASE_RISK
        if name in STRATEGY_BASE_RISK:
            if abs(STRATEGY_BASE_RISK[name] - meta.base_risk) > 1e-9:
                errors.append(
                    f"{name}: STRATEGY_BASE_RISK={STRATEGY_BASE_RISK[name]} "
                    f"!= meta.base_risk={meta.base_risk}"
                )

        # STRATEGY_GDR_THRESHOLDS
        if name in STRATEGY_GDR_THRESHOLDS:
            if STRATEGY_GDR_THRESHOLDS[name] != meta.gdr_thresholds:
                errors.append(
                    f"{name}: STRATEGY_GDR_THRESHOLDS={STRATEGY_GDR_THRESHOLDS[name]} "
                    f"!= meta.gdr_thresholds={meta.gdr_thresholds}"
                )

        # SL_ATR_MULT
        if name in SL_ATR_MULT:
            if SL_ATR_MULT[name] != meta.sl_atr_mult:
                errors.append(
                    f"{name}: SL_ATR_MULT={SL_ATR_MULT[name]} "
                    f"!= meta.sl_atr_mult={meta.sl_atr_mult}"
                )

        # TP_ATR_MULT
        if name in TP_ATR_MULT:
            if TP_ATR_MULT[name] != meta.tp_atr_mult:
                errors.append(
                    f"{name}: TP_ATR_MULT={TP_ATR_MULT[name]} "
                    f"!= meta.tp_atr_mult={meta.tp_atr_mult}"
                )

        # MAX_HOLD_DAYS
        if name in MAX_HOLD_DAYS:
            if MAX_HOLD_DAYS[name] != meta.max_hold_days:
                errors.append(
                    f"{name}: MAX_HOLD_DAYS={MAX_HOLD_DAYS[name]} "
                    f"!= meta.max_hold_days={meta.max_hold_days}"
                )

    return errors
