import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

test('retired Event Radar has no frontend route, panel, or locale registration', () => {
  const dock = fs.readFileSync('src/components/QuickTradePanel/QuickTradePanel.vue', 'utf8')
  const api = fs.readFileSync('src/api/quick-trade.js', 'utf8')
  const locales = fs.readFileSync('src/locales/index.js', 'utf8')

  assert.doesNotMatch(dock, /eventRadar|EventRadar/)
  assert.doesNotMatch(api, /event-radar/)
  assert.doesNotMatch(locales, /eventRadarMessages|event-radar/)
})
