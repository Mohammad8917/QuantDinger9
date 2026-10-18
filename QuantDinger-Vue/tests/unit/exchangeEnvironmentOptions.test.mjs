import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  getCryptoEnvironmentValues,
  normalizeCryptoExchangeId,
  shouldShowCryptoEnvironmentHint
} from '../../src/components/ExchangeAccountModal/environmentOptions.js'

const modalSource = readFileSync(
  new URL('../../src/components/ExchangeAccountModal/ExchangeAccountModal.vue', import.meta.url),
  'utf8'
)

test('normalizes exchange identifiers before resolving environments', () => {
  assert.equal(normalizeCryptoExchangeId(' Binance '), 'binance')
  assert.deepEqual(getCryptoEnvironmentValues(' Binance '), ['live', 'demo'])
})

test('returns each exchange environment contract', () => {
  assert.deepEqual(getCryptoEnvironmentValues('binance'), ['live', 'demo'])
  assert.deepEqual(getCryptoEnvironmentValues('okx'), ['live', 'demo'])
  assert.deepEqual(getCryptoEnvironmentValues('bitget'), ['live', 'demo'])
  assert.deepEqual(getCryptoEnvironmentValues('bybit'), ['live', 'demo'])
  assert.deepEqual(getCryptoEnvironmentValues('gate'), ['live', 'testnet'])
  assert.deepEqual(getCryptoEnvironmentValues('htx'), ['live'])
})

test('falls back to live for an unknown or empty exchange', () => {
  assert.deepEqual(getCryptoEnvironmentValues(''), ['live'])
  assert.deepEqual(getCryptoEnvironmentValues('unknown'), ['live'])
})

test('returns a fresh options array for every render', () => {
  const first = getCryptoEnvironmentValues('binance')
  first.pop()
  assert.deepEqual(getCryptoEnvironmentValues('binance'), ['live', 'demo'])
})

test('shows environment guidance only for demo and test environments', () => {
  assert.equal(shouldShowCryptoEnvironmentHint('live'), false)
  assert.equal(shouldShowCryptoEnvironmentHint(' LIVE '), false)
  assert.equal(shouldShowCryptoEnvironmentHint(''), false)
  assert.equal(shouldShowCryptoEnvironmentHint('demo'), true)
  assert.equal(shouldShowCryptoEnvironmentHint('testnet'), true)
})

test('mounts every account selector dropdown in the modal overlay', () => {
  assert.equal(
    (modalSource.match(/:dropdown-class-name="exchangeSelectDropdownClass"/g) || []).length,
    3
  )
  assert.equal(
    (modalSource.match(/:get-popup-container="getExchangeSelectPopupContainer"/g) || []).length,
    3
  )
})

test('keeps the exchange account modal scoped to crypto credentials', () => {
  assert.doesNotMatch(modalSource, /<a-select-option value="alpaca">/)
  assert.doesNotMatch(modalSource, /<a-select-option value="ibkr">/)
  assert.doesNotMatch(modalSource, /addExchangeType === 'alpaca'/)
  assert.doesNotMatch(modalSource, /addExchangeType === 'ibkr'/)
  assert.doesNotMatch(modalSource, /ibkr_host|ibkr_port|ibkr_client_id|base_url/)
})
