import assert from 'node:assert/strict'
import test from 'node:test'
import { captureChartViewport, restoreChartViewport } from '../../src/utils/chartViewport.mjs'

function rows (count, start = 0) {
  return Array.from({ length: count }, (_, index) => ({ timestamp: start + index * 60_000 }))
}

test('historical viewport follows its timestamp after a full chart data replacement', () => {
  let currentRows = rows(100)
  const scrolls = []
  const chart = {
    getDataList: () => currentRows,
    getVisibleRange: () => ({ from: 20.25, to: 50.25, realFrom: 21, realTo: 50 }),
    scrollToDataIndex: (index, duration) => scrolls.push([index, duration])
  }

  const snapshot = captureChartViewport(chart)
  currentRows = [...currentRows, ...rows(2, 100 * 60_000)]

  assert.equal(snapshot.followingLatest, false)
  assert.equal(restoreChartViewport(chart, snapshot), true)
  assert.deepEqual(scrolls, [[50, 0]])
})

test('historical viewport follows the same right-edge timestamp after older bars are prepended', () => {
  let currentRows = rows(100, 10 * 60_000)
  const scrolls = []
  const chart = {
    getDataList: () => currentRows,
    getVisibleRange: () => ({ from: 20, to: 50, realFrom: 20, realTo: 50 }),
    scrollToDataIndex: (index, duration) => scrolls.push([index, duration])
  }

  const snapshot = captureChartViewport(chart)
  currentRows = [...rows(10), ...currentRows]

  assert.equal(restoreChartViewport(chart, snapshot), true)
  assert.deepEqual(scrolls, [[60, 0]])
})

test('latest viewport keeps following new bars without forced restoration', () => {
  const scrolls = []
  const chart = {
    getDataList: () => rows(100),
    getVisibleRange: () => ({ from: 70, to: 104, realFrom: 70, realTo: 99 }),
    scrollToDataIndex: (...args) => scrolls.push(args)
  }

  const snapshot = captureChartViewport(chart)

  assert.deepEqual(snapshot, { followingLatest: true })
  assert.equal(restoreChartViewport(chart, snapshot), false)
  assert.deepEqual(scrolls, [])
})

test('future whitespace created by dragging candles left survives a data replacement', () => {
  let rightOffsetDistance = 248
  const scrolls = []
  const chart = {
    getDataList: () => rows(100),
    getVisibleRange: () => ({ from: 58, to: 100, realFrom: 88, realTo: 130 }),
    getOffsetRightDistance: () => rightOffsetDistance,
    getBarSpace: () => 8,
    scrollByDistance: (distance, duration) => scrolls.push([distance, duration])
  }

  const snapshot = captureChartViewport(chart)
  rightOffsetDistance = 64

  assert.deepEqual(snapshot, { followingLatest: false, rightOffsetDistance: 248 })
  assert.equal(restoreChartViewport(chart, snapshot), true)
  assert.deepEqual(scrolls, [[-184, 0]])
})
