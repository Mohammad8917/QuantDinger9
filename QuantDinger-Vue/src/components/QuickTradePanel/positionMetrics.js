const finiteNumber = value => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function calculatePositionMetrics (position, isSwapMode) {
  const source = position || {}
  const size = Math.abs(finiteNumber(source.size))
  const entryPrice = finiteNumber(source.entry_price)
  const markPrice = finiteNumber(source.mark_price)
  const leverage = Math.max(finiteNumber(source.leverage), 1)
  const entryNotional = size > 0 && entryPrice > 0 ? size * entryPrice : 0
  const fallbackCurrentValue = size > 0 && markPrice > 0 ? size * markPrice : 0
  const suppliedCurrentValue = Math.abs(finiteNumber(source.notional_usdt))
  const currentValue = suppliedCurrentValue > 0 ? suppliedCurrentValue : fallbackCurrentValue
  const suppliedMargin = Math.abs(finiteNumber(source.initial_margin))
  const inferredLeverage = suppliedMargin > 0 && currentValue > 0
    ? Math.max(Math.round(currentValue / suppliedMargin), 1)
    : leverage
  const effectiveLeverage = isSwapMode && leverage <= 1 && inferredLeverage > 1
    ? inferredLeverage
    : leverage
  const investedAmount = isSwapMode
    ? (suppliedMargin > 0 ? suppliedMargin : (entryNotional > 0 ? entryNotional / effectiveLeverage : 0))
    : entryNotional
  const unrealizedPnl = finiteNumber(source.unrealized_pnl)
  const pnlPercent = investedAmount > 0 ? (unrealizedPnl / investedAmount) * 100 : null

  return {
    invested_amount: investedAmount,
    current_value: currentValue,
    pnl_percent: Number.isFinite(pnlPercent) ? pnlPercent : null,
    effective_leverage: effectiveLeverage
  }
}
