<template>
  <section class="strategy-review-report strategy-tab-pane-inner" :class="{ 'theme-dark': isDark }" data-testid="strategy-review-v2">
    <header class="review-toolbar">
      <div><h2>{{ $t('strategyReviewV2.title') }}</h2><p class="muted">{{ $t('strategyReviewV2.subtitle') }}</p></div>
      <div class="review-actions">
        <a-select
          class="history-select"
          :value="selectedHistoryId"
          :loading="historyLoading"
          :disabled="loading"
          :placeholder="$t('strategyReviewV2.history')"
          :aria-label="$t('strategyReviewV2.history')"
          allow-clear
          @change="selectHistory">
          <a-select-option v-for="item in history" :key="item.id" :value="item.id">{{ historyLabel(item) }}</a-select-option>
        </a-select>
        <a-select v-model="lookbackDays" :disabled="loading" :aria-label="$t('strategyReviewV2.scope')" class="window-select">
          <a-select-option v-for="days in [7, 30, 90]" :key="days" :value="days">{{ $t('strategyReviewV2.window', { days }) }}</a-select-option>
        </a-select>
        <a-button type="primary" :loading="loading" @click="loadReport"><a-icon type="audit" />{{ $t('strategyReviewV2.generate') }}</a-button>
      </div>
    </header>
    <div class="ai-consent"><a-checkbox v-model="includeAi" :disabled="loading">{{ $t('strategyReviewV2.ai') }}</a-checkbox><span class="muted">{{ $t('strategyReviewV2.aiDisclosure') }}</span></div>
    <a-spin :spinning="loading">
      <a-empty v-if="!report" class="review-empty" :description="$t('strategyReviewV2.empty')" />
      <template v-else>
        <section class="review-verdict" :class="verdictTone" aria-live="polite">
          <div class="verdict-heading"><span class="eyebrow">{{ $t('strategyReviewV2.window', { days: report.lookback_days }) }}</span><span class="status-label">{{ $t('strategyReviewV2.' + aiStatus) }}</span></div>
          <h3>{{ $t('strategyReviewV2.' + (isV2 ? evidence.verdict : 'legacy')) }}</h3>
          <p>{{ ai.summary || $t('strategyReviewV2.summaryFallback') }}</p>
          <div class="verdict-meta"><span>{{ (report.strategy || {}).name }}</span><span>{{ (report.strategy || {}).symbol }} · {{ (report.strategy || {}).timeframe }}</span><span>{{ $t('strategyReviewV2.generated', { time: formatTime(report.generated_at || report.created_at) }) }}</span></div>
        </section>
        <template v-if="isV2">
          <section class="cost-section">
            <div class="section-heading"><h3>{{ $t('strategyReviewV2.costTitle') }}</h3><span class="muted">{{ quoteCurrency }}</span></div>
            <div v-if="facts.before_commission_pnl != null" class="cost-equation">
              <div><span>{{ $t('strategyReviewV2.before') }}</span><strong :class="numberTone(facts.before_commission_pnl)">{{ formatNumber(facts.before_commission_pnl) }}</strong></div><span class="operator" aria-hidden="true">−</span>
              <div><span>{{ $t('strategyReviewV2.fee') }}</span><strong class="cost-value">{{ formatNumber(facts.commission) }}</strong></div><span class="operator" aria-hidden="true">=</span>
              <div><span>{{ $t('strategyReviewV2.net') }}</span><strong :class="numberTone(facts.window_net_pnl)">{{ formatNumber(facts.window_net_pnl) }}</strong></div>
            </div>
            <a-alert v-else type="warning" show-icon :message="$t(facts.closed_fill_count ? 'strategyReviewV2.costUnavailable' : 'strategyReviewV2.noTrades')" />
            <p class="muted note">{{ $t('strategyReviewV2.costNote') }}</p>
            <div class="metric-strip">
              <div><span>{{ $t('strategyReviewV2.closed') }}</span><b>{{ facts.closed_fill_count }}</b></div><div><span>{{ $t('strategyReviewV2.profitFactor') }}</span><b>{{ profitFactorText }}</b></div>
              <div><span>{{ $t('strategyReviewV2.payoff') }}</span><b>{{ formatNumber(facts.payoff_ratio) }}</b></div><div><span>{{ $t('strategyReviewV2.average') }}</span><b :class="numberTone(facts.avg_net_per_close)">{{ formatNumber(facts.avg_net_per_close) }}</b></div>
            </div>
            <p v-if="facts.median_holding_seconds != null" class="muted">{{ $t('strategyReviewV2.holding') }}: {{ formatNumber(facts.median_holding_seconds, 0) }} · {{ $t('strategyReviewV2.holdingNote') }}</p>
          </section>
          <section v-if="charts.length" class="evidence-charts" :aria-label="$t('strategyReviewV2.chartTitle')">
            <figure v-for="chart in charts" :key="chart.code" class="evidence-chart">
              <figcaption><h4>{{ $t('strategyReviewV2.chart.' + chart.code) }}</h4><span class="muted">{{ quoteCurrency }}</span></figcaption>
              <div v-for="row in chart.rows" :key="row.code" class="chart-row">
                <div class="chart-label"><span>{{ row.label }} <small v-if="row.count != null">{{ $t('strategyReviewV2.chartCount', { count: row.count, known: row.known }) }}</small></span><b :class="numberTone(row.value)">{{ formatNumber(row.value) }}</b></div>
                <svg viewBox="0 0 1000 22" preserveAspectRatio="none" aria-hidden="true" focusable="false">
                  <line x1="0" x2="1000" y1="21" y2="21" class="chart-baseline" />
                  <line :x1="chartX(chart, 0)" :x2="chartX(chart, 0)" y1="0" y2="22" class="chart-zero" />
                  <rect
                    :x="Math.min(chartX(chart, 0), chartX(chart, row.value))"
                    :width="Math.abs(chartX(chart, row.value) - chartX(chart, 0))"
                    y="4"
                    height="13"
                    rx="2"
                    :class="row.value < 0 ? 'bar-negative' : 'bar-positive'" />
                </svg>
              </div>
              <div class="chart-axis"><span>{{ formatNumber(chart.min) }}</span><span>{{ formatNumber(chart.max) }}</span></div>
              <p class="muted chart-note">{{ $t('strategyReviewV2.chartNote.' + chart.code) }}</p>
            </figure>
          </section>
          <section class="investigations">
            <div class="section-heading"><div><h3>{{ $t('strategyReviewV2.questions') }}</h3><p class="muted">{{ $t('strategyReviewV2.questionsHint') }}</p></div><a-button :aria-expanded="showTrades" aria-controls="review-trades" @click="showTrades = !showTrades">{{ $t('strategyReviewV2.samples') }}<a-icon type="arrow-down" /></a-button></div>
            <article v-for="(issue, index) in issues" :key="issue.code" class="investigation">
              <div class="issue-number">{{ String(index + 1).padStart(2, '0') }}</div>
              <div class="issue-body">
                <div class="issue-heading"><h4>{{ $t('strategyReviewV2.issue.' + issue.code + '.title') }}</h4></div>
                <div class="qa-problem"><span class="qa-label">{{ $t('strategyReviewV2.problem') }}</span><p>{{ annotation(issue).interpretation || $t(issue.finding ? 'strategyReviewV2.finding.' + issue.finding : 'strategyReviewV2.issue.' + issue.code + '.why') }}</p></div>
                <div class="evidence-chips"><span class="muted">{{ $t('strategyReviewV2.evidence') }}</span><span v-for="key in issue.evidence_keys" :key="key">{{ factLabel(key) }} <b>{{ factValue(key) }}</b></span></div>
                <div class="adjustment"><span>{{ $t('strategyReviewV2.optimize') }}</span><p>{{ annotation(issue).proposed_change || adjustmentText(issue) }}</p></div>
                <p class="muted safeguard"><b>{{ $t('strategyReviewV2.safeguard') }}</b> {{ annotation(issue).tradeoff || $t('strategyReviewV2.experiment.' + issue.experiment + '.risk') }}</p>
                <p v-if="issue.code === 'frequency_check'" class="muted note">{{ $t('strategyReviewV2.frequencyNote') }}</p>
                <p v-if="issue.code === 'risk_check'" class="muted note">{{ $t('strategyReviewV2.riskNote') }}</p>
                <details v-if="issue.code === 'exits_check'" class="exit-breakdown">
                  <summary>{{ $t('strategyReviewV2.exitBreakdown') }}</summary>
                  <p class="muted">{{ $t('strategyReviewV2.exitNote') }}</p>
                  <div class="table-scroll" tabindex="0" :aria-label="$t('strategyReviewV2.exitBreakdown')">
                    <table><thead><tr><th>{{ $t('strategyReviewV2.exitReason') }}</th><th>{{ $t('strategyReviewV2.closed') }}</th><th>{{ $t('strategyReviewV2.pnlCount') }}</th><th>{{ $t('strategyReviewV2.pnl') }}</th></tr></thead><tbody>
                      <tr v-for="group in evidence.exit_groups || []" :key="group.code"><td>{{ $t('strategyReviewV2.exit.' + group.code) }}</td><td>{{ group.count }}</td><td>{{ group.pnl_count }}</td><td :class="numberTone(group.net_pnl)">{{ formatNumber(group.net_pnl) }}</td></tr>
                    </tbody></table>
                  </div>
                </details>
              </div>
            </article>
          </section>
          <section v-if="showTrades" id="review-trades" class="trade-evidence">
            <h3>{{ $t('strategyReviewV2.samples') }}</h3><p class="muted">{{ $t('strategyReviewV2.samplesNote') }}</p>
            <div class="table-scroll" tabindex="0" :aria-label="$t('strategyReviewV2.samples')">
              <table><thead><tr><th scope="col">{{ $t('strategyReviewV2.time') }}</th><th scope="col">{{ $t('strategyReviewV2.type') }}</th><th scope="col">{{ $t('strategyReviewV2.price') }}</th><th scope="col">{{ $t('strategyReviewV2.pnl') }}</th></tr></thead>
                <tbody><tr v-for="(trade, i) in evidence.trade_samples" :key="String(trade.id) + ':' + i"><td>{{ formatTime(trade.created_at) }}</td><td>{{ trade.type }}</td><td>{{ formatNumber(trade.price, 6) }}</td><td :class="numberTone(trade.profit)">{{ formatNumber(trade.profit) }}</td></tr></tbody>
              </table><p v-if="!evidence.trade_samples.length" class="muted">{{ $t('strategyReviewV2.noTrades') }}</p>
            </div>
          </section>
          <details class="report-details">
            <summary>{{ $t('strategyReviewV2.limitations') }}<span>{{ evidence.coverage.gaps.length }}</span></summary>
            <p>{{ $t(evidence.source.available ? 'strategyReviewV2.source' : 'strategyReviewV2.sourceMissing') }} <span v-if="evidence.source.version_id">· {{ $t('strategyReviewV2.version', { id: evidence.source.version_id }) }}</span></p>
            <code v-if="evidence.source.hash">{{ evidence.source.hash }}</code>
            <template v-if="evidence.checks">
              <h4>{{ $t('strategyReviewV2.settingsTitle') }}</h4><p>{{ $t('strategyReviewV2.settingsNote') }}</p>
              <div class="evidence-chips"><span v-for="(setting, i) in evidence.current_settings || []" :key="i"><code>{{ setting.key }}</code> <b>{{ formatNumber(setting.value, 4) }}</b> · {{ $t('strategyReviewV2.origin.' + setting.origin) }}</span></div>
              <p v-if="!(evidence.current_settings || []).length">{{ $t('strategyReviewV2.settingsMissing') }}</p>
            </template>
            <ul><li v-for="gap in evidence.coverage.gaps" :key="gap">{{ $t('strategyReviewV2.gap.' + gap) }}</li></ul>
            <h4>{{ $t('strategyReviewV2.fullHistory') }}</h4><p>{{ $t('strategyReviewV2.return') }} {{ formatNumber(metrics.performance_total_return_pct) }}% · {{ $t('strategyReviewV2.drawdown') }} {{ formatNumber(metrics.performance_max_drawdown_pct) }}%</p>
            <p v-if="ai.model" class="muted">{{ ai.provider }} · {{ ai.model }} · {{ ai.elapsed_ms }} ms</p>
          </details>
        </template>
        <section v-else class="legacy-report">
          <a-alert type="info" show-icon :message="$t('strategyReviewV2.legacyHint')" />
          <h3>{{ $t('strategyReview.aiDiagnosis') }}</h3><ul><li v-for="(line, i) in ai.diagnosis || []" :key="i">{{ line }}</li></ul>
          <h3>{{ $t('strategyReview.aiRecommendations') }}</h3><ul><li v-for="(line, i) in ai.recommendations || []" :key="i">{{ line }}</li></ul>
        </section>
      </template>
    </a-spin>
  </section>
</template>

<script>
import { getStrategyReviewReport, getStrategyReviewReportHistory } from '@/api/strategy'

export default {
  name: 'StrategyReviewReport',
  props: { strategyId: { type: [Number, String], default: null }, isDark: { type: Boolean, default: false }, botType: { type: String, default: '' } },
  data () { return { loading: false, historyLoading: false, report: null, history: [], selectedHistoryId: undefined, lookbackDays: 30, includeAi: true, showTrades: false, requestSequence: 0, historySequence: 0 } },
  computed: {
    isV2 () { return this.report && this.report.schema_version === 2 && !!this.report.evidence },
    evidence () { return (this.report && this.report.evidence) || {} },
    facts () { return this.evidence.facts || {} },
    issues () { return (this.evidence.checks && this.evidence.checks.length ? this.evidence.checks : this.evidence.issues) || [] },
    metrics () { return (this.report && this.report.metrics) || {} },
    ai () { return (this.report && this.report.ai) || {} },
    aiStatus () { return this.ai.status === 'ok' ? 'ready' : this.ai.status === 'fallback' ? 'fallback' : 'skipped' },
    verdictTone () { return this.evidence.verdict === 'review_required' ? 'needs-review' : '' },
    quoteCurrency () {
      const symbol = String((this.report && this.report.strategy && this.report.strategy.symbol) || '').toUpperCase().split('@')[0]
      if (symbol.includes('/')) return symbol.split('/')[1].split(':')[0]
      return ['USDT', 'USDC', 'USD', 'BTC', 'ETH'].find(unit => symbol.endsWith(unit)) || ''
    },
    profitFactorText () { return this.facts.profit_factor_state === 'no_losses' ? this.$t('strategyReviewV2.noLosses') : this.formatNumber(this.facts.profit_factor) },
    charts () {
      const finite = value => value != null && Number.isFinite(Number(value))
      const chart = (code, rows) => {
        const usable = rows.filter(row => finite(row.value)).map(row => ({ ...row, value: Number(row.value) }))
        return { code, rows: usable, min: Math.min(0, ...usable.map(row => row.value)), max: Math.max(0, ...usable.map(row => row.value)) }
      }
      const result = []
      if (finite(this.facts.before_commission_pnl) && finite(this.facts.commission) && finite(this.facts.window_net_pnl)) {
        result.push(chart('cost', [
          { code: 'before', label: this.$t('strategyReviewV2.before'), value: this.facts.before_commission_pnl },
          { code: 'fee', label: this.$t('strategyReviewV2.feeImpact'), value: -this.facts.commission },
          { code: 'net', label: this.$t('strategyReviewV2.net'), value: this.facts.window_net_pnl }
        ]))
      }
      if ((this.evidence.coverage || {}).cost_usable !== false) {
        for (const [code, groups, prefix] of [['exits', this.evidence.exit_groups, 'exit.'], ['holding', this.evidence.holding_groups, 'holdingBucket.']]) {
          const rows = (groups || []).filter(group => group.count > 0).map(group => ({ code: group.code, label: this.$t('strategyReviewV2.' + prefix + group.code), count: group.count, known: group.pnl_count, value: group.net_pnl }))
          const entry = chart(code, rows)
          if (entry.rows.length) result.push(entry)
        }
      }
      return result
    }
  },
  watch: {
    strategyId () { this.requestSequence++; this.historySequence++; this.loading = false; this.report = null; this.history = []; this.showTrades = false; this.selectedHistoryId = undefined; this.loadHistory() }
  },
  mounted () { this.loadHistory() },
  beforeDestroy () { this.requestSequence++; this.historySequence++ },
  methods: {
    async loadReport () {
      if (!this.strategyId || this.loading) return
      const seq = ++this.requestSequence
      this.loading = true
      try {
        const res = await getStrategyReviewReport(this.strategyId, { lookback_days: this.lookbackDays, include_ai: this.includeAi, language: this.$i18n.locale })
        if (res && res.data && res.data.billing && res.data.billing.remaining != null) this.$root.$emit('credits-updated', res.data.billing.remaining)
        if (seq !== this.requestSequence) return
        if (!res || res.code !== 1 || !res.data) throw new Error('review_unavailable')
        this.report = res.data
        this.showTrades = false
        this.selectedHistoryId = res.data.history_id || undefined
        this.loadHistory()
      } catch (err) {
        if (seq === this.requestSequence) this.$message.error(this.$t('strategyReview.loadFailed'))
      } finally { if (seq === this.requestSequence) this.loading = false }
    },
    async loadHistory () {
      if (!this.strategyId) return
      const seq = ++this.historySequence
      this.historyLoading = true
      try {
        const res = await getStrategyReviewReportHistory(this.strategyId, { limit: 20 })
        if (seq === this.historySequence) this.history = res && res.code === 1 && Array.isArray(res.data) ? res.data : []
      } catch (err) {
        if (seq === this.historySequence) this.history = []
      } finally { if (seq === this.historySequence) this.historyLoading = false }
    },
    async selectHistory (id) {
      this.selectedHistoryId = id
      if (!id || this.loading) return
      const seq = ++this.requestSequence
      this.loading = true
      try {
        const res = await getStrategyReviewReportHistory(this.strategyId, { report_id: id })
        if (seq !== this.requestSequence) return
        if (!res || res.code !== 1 || !res.data) throw new Error('review_unavailable')
        this.report = res.data
        this.showTrades = false
        this.lookbackDays = res.data.lookback_days || 30
      } catch (err) {
        if (seq === this.requestSequence) this.$message.error(this.$t('strategyReview.historyLoadFailed'))
      } finally { if (seq === this.requestSequence) this.loading = false }
    },
    annotation (issue) { return (Array.isArray(this.ai.issues) && this.ai.issues.find(item => item.code === issue.code)) || {} },
    adjustmentText (issue) {
      return this.$t(issue.finding ? 'strategyReviewV2.action.' + issue.finding : 'strategyReviewV2.experiment.' + issue.experiment + '.change')
    },
    chartX (chart, value) { return chart.max === chart.min ? 500 : (value - chart.min) / (chart.max - chart.min) * 1000 },
    factLabel (key) {
      const diagnosticKeys = ['events_per_day', 'closes_per_day', 'stop_loss_fills', 'stop_loss_net', 'take_profit_fills', 'take_profit_net', 'exit_reason_coverage_pct', 'configured_leverage', 'worst_close_loss', 'worst_close_initial_pct', 'liquidation_fills']
      if (diagnosticKeys.includes(key)) return this.$t('strategyReviewV2.fact.' + key)
      const labels = { window_net_pnl: 'net', before_commission_pnl: 'before', commission: 'fee', closed_fill_count: 'closed', profit_factor: 'profitFactor', avg_net_per_close: 'average', top_5_profit_share: 'concentration', max_consecutive_losses: 'streak', short_hold_count: 'shortCount', short_hold_net_pnl: 'shortNet', short_hold_threshold_seconds: 'shortThreshold' }
      return this.$t('strategyReviewV2.' + (labels[key] || 'notAvailable'))
    },
    factValue (key) {
      if (key === 'profit_factor') return this.profitFactorText
      if (key === 'top_5_profit_share') return this.facts[key] == null ? this.formatNumber(null) : this.formatNumber(this.facts[key] * 100) + '%'
      if (this.facts[key] != null && (key.endsWith('_pct') || key === 'configured_leverage')) return this.formatNumber(this.facts[key]) + (key === 'configured_leverage' ? '×' : '%')
      return this.formatNumber(this.facts[key], ['closed_fill_count', 'max_consecutive_losses', 'short_hold_count', 'stop_loss_fills', 'take_profit_fills', 'liquidation_fills'].includes(key) ? 0 : 2)
    },
    historyLabel (item) { return `${this.formatTime(item.created_at)} · ${this.$t('strategyReviewV2.window', { days: item.lookback_days })} · ${this.formatNumber(item.total_net_pnl)}` },
    formatNumber (value, digits = 2) { return value == null || !Number.isFinite(Number(value)) ? this.$t('strategyReviewV2.notAvailable') : Number(value).toLocaleString(this.$i18n.locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }) },
    formatTime (value) {
      if (!value) return this.$t('strategyReviewV2.notAvailable')
      const numeric = Number(value)
      const date = new Date(Number.isFinite(numeric) ? (numeric > 100000000000 ? numeric : numeric * 1000) : value)
      return Number.isNaN(date.getTime()) ? this.$t('strategyReviewV2.notAvailable') : date.toLocaleString(this.$i18n.locale)
    },
    numberTone (value) { return value == null || !Number.isFinite(Number(value)) ? '' : Number(value) < 0 ? 'negative' : Number(value) > 0 ? 'positive' : '' }
  }
}
</script>

<style scoped>
.strategy-review-report {
  --review-text: var(--sc-text, #182230);
  --review-heading: var(--sc-heading, #111827);
  --review-muted: var(--sc-muted, #667085);
  --review-line: var(--sc-border, #e1e6ec);
  --review-line-soft: var(--sc-border-soft, #ebeff3);
  --review-surface: var(--sc-surface-subtle, #f8fafb);
  --review-surface-muted: var(--sc-surface-muted, #f1f4f7);
  --review-positive: var(--sc-positive, #218653);
  --review-negative: var(--sc-negative, #d14f5a);
  --review-warning: var(--sc-warning, #b37816);
  padding: 0 0 18px;
  color: var(--review-text);
  font-size: 13px;
  line-height: 1.55;
}
h2, h3, h4, p { margin: 0; color: inherit; }
h2 { color: var(--review-heading); font-size: 16px; font-weight: 650; line-height: 1.35; }
h3 { color: var(--review-heading); font-size: 15px; font-weight: 650; line-height: 1.4; }
h4 { color: var(--review-heading); font-size: 14px; font-weight: 650; line-height: 1.45; }
.muted { color: var(--review-muted); font-size: 12px; }
.review-toolbar, .review-actions, .section-heading, .verdict-heading, .issue-heading, .plan-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.review-toolbar { margin-bottom: 8px; }
.review-toolbar > div:first-child { min-width: 0; }
.review-toolbar > div:first-child .muted { margin-top: 2px; }
.review-actions { justify-content: flex-end; flex-wrap: wrap; gap: 6px; }
.review-actions ::v-deep .ant-btn, .review-actions ::v-deep .ant-select-selection { min-height: 32px; border-radius: var(--sc-radius-sm, 6px); }
.history-select { width: 220px; }
.window-select { width: 138px; }
.ai-consent { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; min-height: 36px; margin-bottom: 10px; padding: 7px 10px; border: 1px solid var(--review-line-soft); border-radius: var(--sc-radius-sm, 6px); background: var(--review-surface); }
.ai-consent ::v-deep .ant-checkbox-wrapper { color: var(--review-text); font-size: 12px; }
.theme-dark ::v-deep .ant-btn:not(.ant-btn-primary), .theme-dark ::v-deep .ant-select-selection { color: var(--review-text); background: var(--review-surface); border-color: var(--review-line); }
.theme-dark ::v-deep .ant-select-arrow, .theme-dark ::v-deep .ant-select-selection__placeholder { color: var(--review-muted); }
.review-verdict { padding: 14px 16px; border: 1px solid var(--review-line); border-left: 2px solid var(--primary-color, #52c41a); border-radius: var(--sc-radius-md, 8px); background: var(--review-surface); }
.review-verdict.needs-review { border-left-color: var(--review-warning); }
.eyebrow, .status-label, .hypothesis-label { color: var(--review-muted); font-size: 11px; line-height: 1.35; }
.status-label { padding: 2px 6px; border: 1px solid var(--review-line); border-radius: 999px; background: var(--sc-surface, #fff); }
.review-verdict h3 { margin: 6px 0 5px; font-size: 16px; letter-spacing: -.01em; }
.review-verdict p { max-width: 1120px; color: var(--review-text); line-height: 1.58; white-space: pre-wrap; overflow-wrap: anywhere; }
.verdict-meta { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 9px; color: var(--review-muted); font-size: 11px; }
.cost-section { margin-top: 12px; padding: 14px 0 12px; border-top: 1px solid var(--review-line-soft); border-bottom: 1px solid var(--review-line-soft); }
.section-heading { margin-bottom: 8px; }
.cost-equation { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr); align-items: stretch; gap: 8px; padding: 0 0 8px; }
.cost-equation > div { display: flex; flex-direction: column; justify-content: center; gap: 3px; min-width: 0; padding: 10px 12px; border: 1px solid var(--review-line-soft); border-radius: var(--sc-radius-sm, 6px); background: var(--review-surface); }
.cost-equation > div > span { overflow: hidden; color: var(--review-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.cost-equation strong { overflow: hidden; font-size: 18px; font-weight: 650; font-variant-numeric: tabular-nums; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.operator { align-self: center; color: var(--review-muted); font-size: 16px; }
.cost-value { color: var(--review-warning); }
.negative { color: var(--review-negative); }
.positive { color: var(--review-positive); }
.note { max-width: 1120px; margin: 4px 0 10px; line-height: 1.5; }
.metric-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid var(--review-line-soft); border-radius: var(--sc-radius-sm, 6px); background: var(--review-line-soft); }
.metric-strip > div { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 9px 11px; background: var(--sc-surface, #fff); }
.metric-strip span { overflow: hidden; color: var(--review-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.metric-strip b { overflow: hidden; font-size: 16px; font-weight: 650; font-variant-numeric: tabular-nums; text-overflow: ellipsis; white-space: nowrap; }
.evidence-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 310px), 1fr)); gap: 10px; margin: 12px 0 0; }
.evidence-chart { min-width: 0; margin: 0; padding: 13px 14px; border: 1px solid var(--review-line); border-radius: var(--sc-radius-md, 8px); background: var(--sc-surface, #fff); }
.evidence-chart figcaption { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.chart-row { margin-top: 9px; }
.chart-label { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 12px; }
.chart-label small { display: block; color: var(--review-muted); font-size: 10px; }
.chart-label b { white-space: nowrap; font-variant-numeric: tabular-nums; }
.chart-row svg { display: block; width: 100%; height: 18px; margin-top: 4px; overflow: visible; }
.chart-baseline { stroke: var(--review-line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.chart-zero { stroke: var(--review-muted); stroke-width: 1; vector-effect: non-scaling-stroke; }
.bar-negative { fill: var(--review-negative); }
.bar-positive { fill: var(--review-positive); }
.chart-axis { display: flex; justify-content: space-between; margin-top: 5px; color: var(--review-muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.chart-note { margin-top: 9px; font-size: 11px; line-height: 1.5; }
.investigations { padding-top: 16px; }
.investigations > .section-heading { padding-bottom: 8px; border-bottom: 1px solid var(--review-line-soft); }
.qa-label { display: block; margin-bottom: 3px; color: var(--review-muted); font-size: 11px; font-weight: 600; }
.qa-problem p { max-width: 1120px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.safeguard { margin-bottom: 6px; }
.investigation { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 10px; padding: 14px 0; border-bottom: 1px solid var(--review-line-soft); }
.issue-number { display: inline-flex; width: 24px; height: 24px; align-items: center; justify-content: center; border: 1px solid var(--review-line); border-radius: 50%; color: var(--review-muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.issue-body { min-width: 0; }
.issue-heading { margin-bottom: 6px; flex-wrap: wrap; gap: 6px; }
.issue-body > p { max-width: 1120px; overflow-wrap: anywhere; }
.adjustment { margin: 9px 0; padding: 9px 11px; border: 1px solid color-mix(in srgb, var(--review-warning) 24%, var(--review-line)); border-radius: var(--sc-radius-sm, 6px); background: color-mix(in srgb, var(--review-warning) 5%, var(--review-surface)); }
.adjustment > span { display: block; margin-bottom: 3px; color: var(--review-warning); font-size: 11px; font-weight: 650; }
.adjustment p { max-width: 1120px; line-height: 1.55; overflow-wrap: anywhere; }
.exit-breakdown { margin: 8px 0; }
.evidence-chips { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin: 8px 0; color: var(--review-muted); font-size: 11px; }
.evidence-chips b { margin-left: 4px; color: var(--review-text); font-weight: 650; }
summary { padding: 7px 0; font-weight: 600; cursor: pointer; }
summary > span { margin-left: 10px; color: var(--review-muted); font-size: 11px; font-weight: 400; }
summary:focus-visible, .table-scroll:focus-visible { outline: 2px solid var(--primary-color, #52c41a); outline-offset: 3px; }
.trade-evidence { padding: 16px 0; }
.table-scroll { margin-top: 10px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--review-line-soft); white-space: nowrap; }
th { color: var(--review-muted); font-weight: 500; }
.report-details { margin-top: 14px; color: var(--review-muted); font-size: 12px; }
.report-details li { padding: 3px 0; }
.report-details code { font-size: 11px; overflow-wrap: anywhere; }
.report-details h4 { margin-top: 14px; }
.legacy-report { padding: 16px 0; }
.legacy-report h3 { margin-top: 16px; }
.review-empty { padding: 40px 0; }
@media (max-width: 1100px) {
  .review-toolbar { align-items: flex-start; flex-direction: column; }
  .review-actions { justify-content: flex-start; }
}
@media (max-width: 640px) {
  .review-actions { width: 100%; }
  .history-select { width: 100%; }
  .review-verdict { padding: 12px; }
  .cost-equation { grid-template-columns: 1fr; gap: 6px; }
  .cost-equation > div { flex-direction: row; align-items: center; justify-content: space-between; }
  .operator { display: none; }
  .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .investigation { grid-template-columns: 22px minmax(0, 1fr); gap: 8px; }
  .section-heading, .plan-footer, .verdict-heading { align-items: flex-start; }
}
</style>
