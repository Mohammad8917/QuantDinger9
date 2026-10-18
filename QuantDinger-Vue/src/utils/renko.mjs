function finiteNumber (value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function normalizeRows (rows) {
  return (Array.isArray(rows) ? rows : [])
    .map(row => ({
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

export function calculateRenkoBoxSize (rows, atrLength = 14) {
  const data = normalizeRows(rows)
  if (data.length < 2) return 0

  const trueRanges = []
  for (let index = 1; index < data.length; index += 1) {
    const current = data[index]
    const previous = data[index - 1]
    trueRanges.push(Math.max(
      current.high - current.low,
      Math.abs(current.high - previous.close),
      Math.abs(current.low - previous.close)
    ))
  }

  const sample = trueRanges.slice(-Math.max(1, Number(atrLength) || 14)).filter(value => value > 0)
  const atr = sample.length ? sample.reduce((sum, value) => sum + value, 0) / sample.length : 0
  const lastClose = Math.abs(data[data.length - 1].close)
  const fallback = lastClose > 0 ? lastClose * 0.005 : 0.01
  return Math.max(atr || fallback, fallback * 0.1, Number.EPSILON)
}

export function buildRenkoBricks (rows, options = {}) {
  const data = normalizeRows(rows)
  if (data.length < 2) return []

  const requestedBoxSize = finiteNumber(options.boxSize)
  const boxSize = requestedBoxSize && requestedBoxSize > 0
    ? requestedBoxSize
    : calculateRenkoBoxSize(data, options.atrLength)
  if (!Number.isFinite(boxSize) || boxSize <= 0) return []

  const bricks = []
  let brickClose = data[0].close
  let direction = 0
  let lastTimestamp = data[0].timestamp - 1

  for (let index = 1; index < data.length; index += 1) {
    const row = data[index]
    const difference = row.close - brickClose
    const nextDirection = Math.sign(difference)
    if (!nextDirection) continue

    const reversing = Boolean(direction && nextDirection !== direction)
    const reversalThreshold = reversing ? boxSize * 2 : boxSize
    if (Math.abs(difference) + Number.EPSILON < reversalThreshold) continue

    const distanceInBoxes = Math.floor((Math.abs(difference) + Number.EPSILON) / boxSize)
    const brickCount = reversing ? distanceInBoxes - 1 : distanceInBoxes
    if (!brickCount) continue
    const volumePerBrick = row.volume / brickCount

    for (let brickIndex = 0; brickIndex < brickCount; brickIndex += 1) {
      const open = reversing && brickIndex === 0
        ? brickClose + nextDirection * boxSize
        : brickClose
      const close = reversing && brickIndex === 0
        ? brickClose + nextDirection * boxSize * 2
        : brickClose + nextDirection * boxSize
      const timestamp = Math.max(row.timestamp + brickIndex, lastTimestamp + 1)
      bricks.push({
        timestamp,
        open,
        high: Math.max(open, close),
        low: Math.min(open, close),
        close,
        volume: volumePerBrick
      })
      brickClose = close
      lastTimestamp = timestamp
    }

    direction = nextDirection
  }

  return bricks
}
