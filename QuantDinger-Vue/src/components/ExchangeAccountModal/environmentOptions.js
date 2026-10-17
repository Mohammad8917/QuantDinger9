const LIVE_ENVIRONMENT = 'live'

const ENVIRONMENTS_BY_EXCHANGE = Object.freeze({
  binance: Object.freeze([LIVE_ENVIRONMENT, 'demo']),
  okx: Object.freeze([LIVE_ENVIRONMENT, 'demo']),
  bitget: Object.freeze([LIVE_ENVIRONMENT, 'demo']),
  bybit: Object.freeze([LIVE_ENVIRONMENT, 'demo']),
  gate: Object.freeze([LIVE_ENVIRONMENT, 'testnet']),
  htx: Object.freeze([LIVE_ENVIRONMENT])
})

export function normalizeCryptoExchangeId (exchangeId) {
  return String(exchangeId || '').trim().toLowerCase()
}

export function getCryptoEnvironmentValues (exchangeId) {
  const normalizedId = normalizeCryptoExchangeId(exchangeId)
  return [...(ENVIRONMENTS_BY_EXCHANGE[normalizedId] || [LIVE_ENVIRONMENT])]
}
