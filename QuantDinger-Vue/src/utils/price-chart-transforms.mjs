function finiteNumber (value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function normalizeRows (rows) {
  return (Array.isArray(rows) ? rows : [])
    .map(row => ({
      ...row,
      timestamp: finiteNumber(row && row.timestamp),
      open: finiteNumber(row && row.open),
      high: finiteNumber(row && row.high),
      low: finiteNumber(row && row.low),
      close: finiteNumber(row && row.close),
      volume: finiteNumber(row && row.volume) || 0
    }))
    .filter(row => row.timestamp != null && row.open != null && row.high != null && row.low != null && row.close != null)
    .sort((a, b) => a.timestamp - b.timestamp)
}

export function buildHeikinAshiRows (rows) {
  const data = normalizeRows(rows)
  let previousOpen = null
  let previousClose = null

  return data.map((row, index) => {
    const close = (row.open + row.high + row.low + row.close) / 4
    const open = index === 0
      ? (row.open + row.close) / 2
      : (previousOpen + previousClose) / 2
    const transformed = {
      ...row,
      open,
      high: Math.max(row.high, open, close),
      low: Math.min(row.low, open, close),
      close
    }
    previousOpen = open
    previousClose = close
    return transformed
  })
}

export function buildHlcAreaRows (rows) {
  return normalizeRows(rows).map(row => ({
    ...row,
    close: (row.high + row.low + row.close) / 3
  }))
}

export function calculateRangeSize (rows, atrLength = 14) {
  const data = normalizeRows(rows)
  if (data.length < 2) return 0
  const ranges = []
  for (let index = 1; index < data.length; index += 1) {
    const current = data[index]
    const previous = data[index - 1]
    ranges.push(Math.max(
      current.high - current.low,
      Math.abs(current.high - previous.close),
      Math.abs(current.low - previous.close)
    ))
  }
  const sample = ranges.slice(-Math.max(1, Number(atrLength) || 14)).filter(value => value > 0)
  const atr = sample.length ? sample.reduce((sum, value) => sum + value, 0) / sample.length : 0
  const lastClose = Math.abs(data[data.length - 1].close)
  return Math.max(atr || lastClose * 0.005 || 0.01, Number.EPSILON)
}

export function buildRangeBars (rows, options = {}) {
  const data = normalizeRows(rows)
  if (data.length < 2) return []
  const requestedRange = finiteNumber(options.rangeSize)
  const rangeSize = requestedRange && requestedRange > 0
    ? requestedRange
    : calculateRangeSize(data, options.atrLength)
  if (!Number.isFinite(rangeSize) || rangeSize <= 0) return []

  const bars = []
  let barClose = data[0].close
  let lastTimestamp = data[0].timestamp - 1

  for (let index = 1; index < data.length; index += 1) {
    const row = data[index]
    let remaining = row.close - barClose
    const barCount = Math.floor((Math.abs(remaining) + Number.EPSILON) / rangeSize)
    if (!barCount) continue
    const volumePerBar = row.volume / barCount

    for (let barIndex = 0; barIndex < barCount; barIndex += 1) {
      const direction = Math.sign(remaining)
      const open = barClose
      const close = open + direction * rangeSize
      const timestamp = Math.max(row.timestamp + barIndex, lastTimestamp + 1)
      bars.push({
        timestamp,
        open,
        high: Math.max(open, close),
        low: Math.min(open, close),
        close,
        volume: volumePerBar
      })
      barClose = close
      remaining = row.close - barClose
      lastTimestamp = timestamp
    }
  }

  return bars
}
