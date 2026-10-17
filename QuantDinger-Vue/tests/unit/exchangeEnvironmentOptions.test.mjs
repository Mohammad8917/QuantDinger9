import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getCryptoEnvironmentValues,
  normalizeCryptoExchangeId
} from '../../src/components/ExchangeAccountModal/environmentOptions.js'

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
