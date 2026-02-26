# LLM Sentiment Integration Gate Criteria

## Overview

This document defines the prerequisites for integrating LLM-based sentiment
analysis into the AutoTrader v2 live trading pipeline. Per the business panel
recommendation (Porter, Taleb, Christensen, Meadows, Drucker), LLM sentiment
should NOT be added until all criteria below are met.

## Rationale

Adding LLM sentiment prematurely introduces:
- **Complexity risk**: More failure modes before the base system is validated
- **Cost risk**: API costs without proven benefit (Taleb's via negativa)
- **Signal noise**: Sentiment data may not improve signal quality
- **Dependency risk**: External API availability becomes a trading dependency

## Gate Criteria

All criteria must be met simultaneously before LLM sentiment integration begins.

### 1. Account Size
- **Minimum**: $10,000 account equity
- **Rationale**: API costs (~$50-100/month for GPT-4 calls) should be <1% of account
- **Measurement**: Average account equity over trailing 30 days

### 2. Live Trading Duration
- **Minimum**: 3 months of continuous live trading data
- **Rationale**: Need sufficient data to establish a baseline for A/B comparison
- **Measurement**: Oldest trade record in live_trades.jsonl

### 3. VIX Filter Validated
- **Requirement**: VIX-based sentiment adjustment shows measurable improvement
- **Measurement**: A/B comparison (RotationComparator) shows:
  - Event-driven rotation outperforms weekly-only by >5% on risk-adjusted return
  - OR VIX-adjusted weights show >3% improvement in win rate
- **Rationale**: If the free VIX signal doesn't help, a paid LLM signal likely won't either

### 4. Positive Sharpe Ratio
- **Requirement**: Overall strategy Sharpe ratio > 0.5 over trailing 90 days
- **Rationale**: System must be profitable before adding complexity
- **Measurement**: Computed from equity_snapshots.jsonl using run_live_monitor.py

### 5. Stable Infrastructure
- **Requirement**: No unplanned downtime in trailing 30 days
- **Components**: Alpaca connection, bar streaming, order execution, rotation scheduler
- **Measurement**: System uptime logs

### 6. Maximum Drawdown Control
- **Requirement**: Max drawdown < 20% over trailing 90 days
- **Rationale**: Risk management must be working before adding more signals
- **Measurement**: Peak-to-trough from equity snapshots

## Integration Plan (When Criteria Met)

### Phase 1: Research (1-2 weeks)
- Evaluate LLM providers (OpenAI, Anthropic, local models)
- Define sentiment schema (bullish/bearish/neutral per sector)
- Estimate API costs for daily sentiment analysis

### Phase 2: Shadow Mode (2-4 weeks)
- Run LLM sentiment alongside live trading (no execution impact)
- Log sentiment signals to SQLite for analysis
- Compare sentiment predictions vs actual market moves

### Phase 3: Integration (1-2 weeks)
- Add sentiment as an additional weight modifier (similar to VIX adjustment)
- Start with small weight (5% influence on allocation)
- A/B compare sentiment-enhanced vs base strategy

### Phase 4: Validation (4+ weeks)
- Monitor sentiment impact on live PnL
- Increase/decrease weight based on performance
- Kill switch: disable if win rate drops >5% from baseline

## Potential LLM Sentiment Sources
- Financial news headlines (Reuters, Bloomberg)
- SEC filings (10-K, 10-Q, 8-K summaries)
- Earnings call transcripts
- Social media sentiment (Twitter/X, Reddit)
- Analyst reports and upgrades/downgrades

## Cost Estimation
| Provider | Model | Est. Daily Cost | Monthly |
|----------|-------|----------------|---------|
| OpenAI | GPT-4o-mini | $1-2/day | $30-60 |
| Anthropic | Claude Haiku | $1-3/day | $30-90 |
| Local | Llama 3 | $0 (compute) | $0 |

## Review Schedule
- Check gate criteria monthly using run_live_monitor.py
- Document in data/gate_check_log.jsonl when criteria are evaluated
- Decision requires all 6 criteria met for 2 consecutive monthly checks
