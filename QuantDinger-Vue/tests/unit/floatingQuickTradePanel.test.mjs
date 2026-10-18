import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { clampFloatingPanelPosition, snapFloatingPanelPosition } from '../../src/utils/floatingPanel.mjs'

test('floating panel position stays inside the chart at every edge', () => {
  const dimensions = {
    containerWidth: 1200,
    containerHeight: 800,
    panelWidth: 408,
    panelHeight: 620,
    inset: 10
  }
  assert.deepEqual(clampFloatingPanelPosition({ ...dimensions, x: -200, y: -100 }), { x: 10, y: 10 })
  assert.deepEqual(clampFloatingPanelPosition({ ...dimensions, x: 2000, y: 900 }), { x: 782, y: 170 })
})

test('floating panel snaps only when it is close to a chart edge', () => {
  const dimensions = {
    containerWidth: 1200,
    containerHeight: 800,
    panelWidth: 408,
    panelHeight: 620,
    inset: 10
  }
  assert.deepEqual(snapFloatingPanelPosition({ x: 770, y: 22 }, dimensions), { x: 782, y: 10 })
  assert.deepEqual(snapFloatingPanelPosition({ x: 420, y: 90 }, dimensions), { x: 420, y: 90 })
})

test('indicator IDE keeps every required quick-trade capability in the floating console', async () => {
  const panel = await readFile(new URL('../../src/components/QuickTradePanel/QuickTradePanel.vue', import.meta.url), 'utf8')
  const ide = await readFile(new URL('../../src/views/indicator-ide/index.vue', import.meta.url), 'utf8')
  for (const contract of [
    'floating-console',
    'selectedCredentialId',
    'orderType',
    'limitPrice',
    'spotBuyInputMode',
    'spotSellInputMode',
    'marginMode',
    'leverage',
    'dockTpslEnabled',
    "handleSubmit('buy')",
    "handleSubmit('sell')",
    'dockTabItems'
  ]) assert.match(panel, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))

  for (const contract of [
    'startQuickTradeDrag',
    'toggleQuickTradePin',
    'quickTradeMinimized',
    'quickTradeFloatingStyle'
  ]) assert.match(ide, new RegExp(contract))

  assert.doesNotMatch(ide, /quickTradeAiDecisionFilter/)
  assert.doesNotMatch(ide, /ai-decision-filter-enabled/)
  assert.match(panel, /v-for="percent in \[10, 25, 50, 100\]"/)
  assert.match(panel, /take_profit_price: useProtectionPrices \? Number\(this\.tpPrice \|\| 0\) : 0/)
  assert.match(panel, /stop_loss_price: useProtectionPrices \? Number\(this\.slPrice \|\| 0\) : 0/)
  assert.match(ide, /@price-change="handleChartPriceChange"/)
  assert.match(ide, /handleChartPriceChange \(payload\)/)
  assert.match(ide, /:exchange-id="market === 'Crypto' \? cryptoExchangeId : ''"/)
  assert.match(ide, /@exchange-change="handleQuickTradeExchangeChange"/)
  assert.match(ide, /handleQuickTradeExchangeChange \(context\)/)
  assert.match(panel, /this\.\$emit\('exchange-change', \{/)
  assert.match(panel, /syncCredentialToExchange \(exchangeId\)/)
  assert.match(panel, /String\(selected\.exchange_id \|\| ''\).*=== normalizedExchangeId/)
  assert.doesNotMatch(ide, /this\.qtPrice = 0\s*\n\s*this\.quickTradeMinimized/)
  assert.doesNotMatch(panel, /ai_decision_filter/)
  assert.doesNotMatch(panel, /eventRadar/)
})
