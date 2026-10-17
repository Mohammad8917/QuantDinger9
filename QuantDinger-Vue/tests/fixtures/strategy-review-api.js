const evidence = {
  version: 2, verdict: 'review_required', window: { start: 1789606800, end: 1792198800 },
  facts: { window_net_pnl: -371.34, before_commission_pnl: -26.771096, commission: 344.568904, closed_fill_count: 433, profit_factor: 0.3325, profit_factor_state: 'finite', payoff_ratio: 1.8825, avg_net_per_close: -0.8569, max_consecutive_losses: 54, top_5_profit_share: 0.6 },
  issues: [
    { code: 'negative_edge', priority: 'high', evidence_keys: ['window_net_pnl', 'before_commission_pnl', 'commission'], experiment: 'cost_sensitivity', validation_status: 'not_run' },
    { code: 'signal_quality', priority: 'high', evidence_keys: ['closed_fill_count', 'avg_net_per_close', 'profit_factor'], experiment: 'ma_filter', validation_status: 'not_run' },
    { code: 'concentration', priority: 'medium', evidence_keys: ['top_5_profit_share', 'max_consecutive_losses'], experiment: 'walk_forward', validation_status: 'not_run' }
  ],
  coverage: { gaps: ['market_path', 'funding', 'execution_cost', 'version_continuity', 'fill_not_roundtrip'] },
  source: { available: true, version_id: 12, hash: 'f3963d40a2f475d53b7c4bb6173a987948be599e55f00ee2c09ed3ac3d844ac9' },
  trade_samples: [{ id: 1, created_at: 1792198200, type: 'close_long', price: 67210.5, profit: -1.81 }, { id: 2, created_at: 1792198800, type: 'open_short', price: 67209.1, profit: null }]
}
// Synthetic diagnostic cohorts exercise the UI; they are not the user's live ledger.
Object.assign(evidence.facts, { events_per_day: 28.9, closes_per_day: 14.43, short_hold_count: 180, short_hold_net_pnl: -250, stop_loss_fills: 200, stop_loss_net: -300, take_profit_fills: 65, take_profit_net: 184.83, exit_reason_coverage_pct: 61.2, configured_leverage: 5, worst_close_loss: 8, worst_close_initial_pct: 0.8, liquidation_fills: 0 })
evidence.checks = [
  { code: 'cost_check', status: 'observed', finding: 'cost_negative', evidence_keys: ['window_net_pnl', 'commission', 'before_commission_pnl'], experiment: 'cost_sensitivity' },
  { code: 'frequency_check', status: 'review', finding: 'frequency_short', evidence_keys: ['events_per_day', 'closes_per_day', 'short_hold_count', 'short_hold_net_pnl'], experiment: 'frequency_filter' },
  { code: 'exits_check', status: 'review', finding: 'exits_observed', evidence_keys: ['stop_loss_fills', 'stop_loss_net', 'take_profit_fills', 'take_profit_net', 'exit_reason_coverage_pct'], experiment: 'exit_timing' },
  { code: 'risk_check', status: 'insufficient', finding: 'risk_unknown', evidence_keys: ['configured_leverage', 'worst_close_loss', 'worst_close_initial_pct', 'liquidation_fills'], experiment: 'risk_budget' }
]
evidence.exit_groups = [
  { code: 'stop_loss', count: 200, pnl_count: 200, net_pnl: -300 },
  { code: 'take_profit', count: 65, pnl_count: 65, net_pnl: 184.83 },
  { code: 'unknown', count: 168, pnl_count: 168, net_pnl: -256.17 }
]
evidence.current_settings = [{ key: 'stop_loss_pct', value: 0.01, origin: 'deployment' }]
evidence.holding_groups = [
  { code: 'under_5m', count: 180, pnl_count: 180, net_pnl: -250 },
  { code: '5m_30m', count: 140, pnl_count: 140, net_pnl: -180 },
  { code: '30m_2h', count: 80, pnl_count: 80, net_pnl: -31.34 },
  { code: 'over_2h', count: 33, pnl_count: 33, net_pnl: 90 }
]
export const report = {
  schema_version: 2, generated_at: 1792198800, lookback_days: 30, history_id: 1,
  strategy: { id: 1, name: 'Dual Moving Average · QA', symbol: 'BTC/USDT', timeframe: '1m' },
  evidence, ai: { status: 'skipped', summary: '', issues: [] }, metrics: { performance_total_return_pct: -37.134, performance_max_drawdown_pct: 37.33 }
}
export async function getStrategyReviewReport (id, options) { return { code: 1, data: { ...report, lookback_days: options.lookback_days } } }
export async function getStrategyReviewReportHistory (id, options) {
  return { code: 1, data: options.report_id ? report : [{ id: 1, created_at: report.generated_at, lookback_days: 30, total_net_pnl: -371.34 }] }
}
