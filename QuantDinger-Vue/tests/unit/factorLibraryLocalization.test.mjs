import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import factorLibraryMessages from '../../src/locales/lang/factor-library-enhancements.js'
import talibMessages from '../../src/locales/lang/talib-factors.js'

const root = fileURLToPath(new URL('../../', import.meta.url))
const read = relativePath => fs.readFileSync(`${root}${relativePath}`, 'utf8')
const registrySource = read('../quantdinger_backend/backend_api_python/app/services/factors/registry.py')
const englishSource = read('src/locales/lang/en-US.js')
const chineseSource = read('src/locales/lang/zh-CN.js')
const factorResearchSource = read('src/locales/lang/factor-research-factors.js')
const hanPattern = /\p{Script=Han}/u

function localeValues (source, locale = '') {
  const scoped = locale
    ? source.split(`'${locale}': {`)[1]?.split(/^\s*},?$/m)[0] || ''
    : source
  const values = new Map()
  const pattern = /['"](factor\.[a-z0-9_]+\.(?:name|description))['"]\s*:\s*['"]([^'"\r\n]*)['"]/g
  for (const match of scoped.matchAll(pattern)) values.set(match[1], match[2])
  return values
}

test('every native factor has an English and Simplified Chinese name and description', () => {
  const factorIds = [...registrySource.matchAll(/_(?:technical|fundamental)\("([a-z0-9_]+)"/g)]
    .map(match => match[1])
  const english = new Map([
    ...localeValues(englishSource),
    ...localeValues(factorResearchSource, 'en-US')
  ])
  const chinese = new Map([
    ...localeValues(chineseSource),
    ...localeValues(factorResearchSource, 'zh-CN')
  ])

  assert.equal(new Set(factorIds).size, factorIds.length)
  for (const factorId of factorIds) {
    for (const suffix of ['name', 'description']) {
      const key = `factor.${factorId}.${suffix}`
      assert.ok(english.get(key), `Missing English factor copy: ${key}`)
      assert.ok(chinese.get(key), `Missing Simplified Chinese factor copy: ${key}`)
      assert.equal(hanPattern.test(english.get(key)), false, `English factor copy contains Han text: ${key}`)
    }
  }
})

test('factor-library English enhancements contain no Chinese copy', () => {
  for (const [key, value] of Object.entries(factorLibraryMessages['en-US'])) {
    assert.equal(hanPattern.test(value), false, `English factor-library copy contains Han text: ${key}`)
  }
})

test('dynamic factor explanations exist for every supported locale', () => {
  const requiredKeys = [
    'factorLibrary.qlibFeatureName',
    'factorLibrary.qlibFeatureDescription',
    'factorLibrary.talibFeatureDescription',
    'factorLibrary.whatItMeasures',
    'factorLibrary.howToUse',
    'factorLibrary.watchOut',
    'factorLibrary.caution.modelFeature',
    'factorLibrary.caution.technical',
    'factorLibrary.caution.fundamental'
  ]

  for (const [locale, messages] of Object.entries(factorLibraryMessages)) {
    for (const key of requiredKeys) {
      assert.ok(messages[key], `Missing ${locale} factor-library copy: ${key}`)
    }
  }
})

test('TA-Lib overrides provide localized names and descriptions for every extended indicator', () => {
  const english = talibMessages['en-US']
  const factorIds = Object.keys(english)
    .filter(key => key.startsWith('factor.talib.') && key.endsWith('.name'))
    .map(key => key.slice('factor.talib.'.length, -'.name'.length))

  assert.ok(factorIds.length > 30)
  for (const [locale, messages] of Object.entries(talibMessages)) {
    for (const factorId of factorIds) {
      assert.ok(messages[`factor.talib.${factorId}.name`], `Missing ${locale} TA-Lib name: ${factorId}`)
      assert.ok(messages[`factor.talib.${factorId}.description`], `Missing ${locale} TA-Lib description: ${factorId}`)
    }
  }
})
