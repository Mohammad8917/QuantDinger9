<template>
  <section v-show="history || showEmpty || rows.length || loading || error" class="qtc-position-activity" :aria-busy="loading">
    <div class="qtc-activity-toolbar">
      <span v-if="history" class="qtc-history-context"><strong>{{ symbol }}</strong><span v-if="rows.length">{{ $t('quickTrade.workflow.recent', { count: rows.length }) }}</span><a-tooltip :title="$t('quickTrade.workflow.historyHint')"><a-icon type="info-circle" /></a-tooltip></span>
      <span v-else>{{ $t('quickTrade.workflow.nativeOrders') }}</span>
      <button type="button" class="qtc-refresh" :disabled="loading" :title="$t('quickTrade.workflow.refresh')" :aria-label="$t('quickTrade.workflow.refresh')" @click="load"><a-icon :type="loading ? 'loading' : 'reload'" /></button>
    </div>
    <div v-if="error" class="qtc-activity-empty">{{ error }}</div>
    <div v-else-if="loading && !rows.length" class="qtc-activity-empty" role="status"><a-icon type="loading" /><span>{{ $t(history ? 'quickTrade.workflow.loading' : 'quickTrade.workflow.loadingOrders') }}</span></div>
    <div v-else-if="!supported" class="qtc-activity-empty">{{ $t(history ? 'quickTrade.workflow.historyUnsupported' : 'quickTrade.workflow.protectionUnsupported') }}</div>
    <div v-else-if="!rows.length" class="qtc-activity-empty"><a-icon type="inbox" /><span>{{ $t(history ? 'quickTrade.workflow.empty' : 'quickTrade.noOrders') }}</span></div>
    <div v-else class="qtc-table-scroll">
      <table v-if="history" class="qtc-positions qtc-position-history">
        <thead><tr><th>{{ $t('quickTrade.side') }} / {{ $t('quickTrade.workflow.quantity') }}</th><th>{{ $t('quickTrade.workflow.entry') }}</th><th>{{ $t('quickTrade.workflow.exit') }}</th><th>{{ $t('quickTrade.workflow.fees') }}</th><th>{{ $t('quickTrade.workflow.netPnl') }} (USDT)</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id">
          <td><span class="qtc-side" :class="row.side === 'long' ? 'qtc-positive' : 'qtc-negative'">{{ $t(row.side === 'long' ? 'quickTrade.long' : 'quickTrade.short') }}</span><small>{{ number(row.quantity, 8) }}</small></td>
          <td><span>{{ number(row.entry_price) }}</span><small :title="date(row.opened_at, true)">{{ date(row.opened_at) }}</small></td>
          <td><span>{{ number(row.exit_price) }}</span><small :title="date(row.closed_at, true)">{{ date(row.closed_at) }}</small></td>
          <td>{{ number(row.fee, 6) }}</td>
          <td><a-tooltip><template slot="title">{{ $t('quickTrade.workflow.grossPnl') }}: {{ number(row.gross_pnl, 6) }}<br>{{ $t('quickTrade.workflow.funding') }}: {{ number(row.funding, 6) }}</template><strong class="qtc-pnl" :class="row.pnl == null ? '' : row.pnl >= 0 ? 'qtc-positive' : 'qtc-negative'">{{ row.pnl > 0 ? '+' : '' }}{{ number(row.pnl, 6) }}</strong></a-tooltip></td>
        </tr></tbody>
      </table>
      <table v-else class="qtc-positions"><tbody><tr v-for="row in rows" :key="row.id"><td>{{ $t(row.side === 'long' ? 'quickTrade.long' : 'quickTrade.short') }}</td><td>{{ $t(row.kind === 'tp' ? 'quickTrade.tp' : 'quickTrade.sl') }}</td><td>{{ number(row.price) }}</td><td><a-button type="link" size="small" :loading="cancelling === row.id" :disabled="!!cancelling" @click="cancel(row)">{{ $t('brokerAccounts.cancelOrder') }}</a-button></td></tr></tbody></table>
    </div>
  </section>
</template>

<script>
import { getQuickPositionHistory, getQuickPositionProtection, updateQuickPositionProtection } from '@/api/quick-trade'
export default {
  props: { credentialId: { type: [Number, String], required: true }, symbol: { type: String, required: true }, marketType: { type: String, default: 'swap' }, history: Boolean, showEmpty: Boolean },
  data: () => ({ rows: [], loading: false, error: '', supported: true, cancelling: '', generation: 0 }),
  computed: { context () { return [this.credentialId, this.symbol, this.marketType, this.history].join('|') } },
  watch: { context: { immediate: true, handler () { this.rows = []; this.load() } } },
  beforeDestroy () { this.generation++ },
  methods: {
    number (value, digits = 4) { return value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits }) },
    date (value, full = false) { if (!value) return '—'; const date = new Date(value); return full ? date.toLocaleString() : date.toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) },
    async load () {
      const generation = ++this.generation
      this.loading = true; this.error = ''
      try {
        const res = await (this.history ? getQuickPositionHistory : getQuickPositionProtection)({ credential_id: this.credentialId, symbol: this.symbol, market_type: this.marketType })
        if (generation !== this.generation) return
        if (res.code !== 1) throw new Error(res.msg)
        this.supported = res.data.supported
        this.rows = res.data[this.history ? 'positions' : 'orders'] || []
      } catch (e) { if (generation === this.generation) this.error = this.$t(this.history ? 'quickTrade.workflow.historyFailed' : 'quickTrade.workflow.protectionFailed') } finally { if (generation === this.generation) this.loading = false }
    },
    async cancel (row) {
      if (this.cancelling) return
      this.cancelling = row.id
      try {
        const res = await updateQuickPositionProtection({ credential_id: this.credentialId, symbol: this.symbol, position_side: row.side, action: 'cancel', order_id: row.id })
        if (res.code !== 1) throw new Error(res.msg)
        await this.load()
      } catch (e) { this.$message.error(this.$t('quickTrade.workflow.protectionFailed')) } finally { this.cancelling = '' }
    }
  }
}
</script>

<style lang="less" scoped>
.qtc-position-activity { padding: 0 12px 8px; color: var(--qtc-text); font-size: 12px; font-variant-numeric: tabular-nums; }
.qtc-activity-toolbar { display: flex; justify-content: space-between; align-items: center; min-height: 32px; gap: 8px; color: var(--qtc-muted); }
.qtc-history-context { display: flex; align-items: center; gap: 10px; strong { font-size: 12px; font-weight: 500; color: var(--qtc-text); } }
.qtc-refresh { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; background: transparent; border: 0; border-radius: 4px; color: var(--qtc-muted); cursor: pointer; &:hover:not(:disabled) { color: var(--primary-color); background: var(--qtc-muted-bg); } &:disabled { cursor: default; } }
.qtc-activity-empty { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 68px; padding: 12px; color: var(--qtc-muted); text-align: center; }
.qtc-table-scroll { max-height: 212px; overflow: auto; }
.qtc-positions { width: 100%; border-collapse: collapse; font-size: 12px; line-height: 1.5; th { position: sticky; top: 0; background: var(--qtc-bg); color: var(--qtc-muted); font-weight: 400; text-align: left; z-index: 1; } td, th { padding: 8px 6px; border-bottom: 1px solid var(--qtc-border); white-space: nowrap; } td:nth-last-child(-n+2), th:nth-last-child(-n+2) { text-align: right; } td { vertical-align: middle; } tbody tr:last-child td { border-bottom: 0; } tbody tr:hover { background: var(--qtc-muted-bg); } small { display: block; margin-top: 2px; color: var(--qtc-muted); font-size: 11px; } }
.qtc-side, .qtc-pnl { font-weight: 500; }
.qtc-positive { color: var(--qtc-green); }
.qtc-negative { color: var(--qtc-red); }
</style>
