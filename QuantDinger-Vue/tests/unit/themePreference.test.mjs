import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const preferencePath = fileURLToPath(new URL('../../src/utils/themePreference.js', import.meta.url))
const preferenceSource = fs.readFileSync(preferencePath, 'utf8')
const bootstrapPath = fileURLToPath(new URL('../../src/core/bootstrap.js', import.meta.url))
const bootstrapSource = fs.readFileSync(bootstrapPath, 'utf8')
const appStorePath = fileURLToPath(new URL('../../src/store/modules/app.js', import.meta.url))
const appStoreSource = fs.readFileSync(appStorePath, 'utf8')
const layoutPath = fileURLToPath(new URL('../../src/layouts/BasicLayout.vue', import.meta.url))
const layoutSource = fs.readFileSync(layoutPath, 'utf8')
const drawerPath = fileURLToPath(new URL('../../src/components/SettingDrawer/SettingDrawer.vue', import.meta.url))
const drawerSource = fs.readFileSync(drawerPath, 'utf8')
const indexPath = fileURLToPath(new URL('../../index.html', import.meta.url))
const indexSource = fs.readFileSync(indexPath, 'utf8')

test('theme color uses a durable namespaced preference with legacy fallback', () => {
  assert.match(preferenceSource, /THEME_COLOR_STORAGE_KEY = 'qd-ui-primary-color'/)
  assert.match(preferenceSource, /storage\.get\(THEME_COLOR_STORAGE_KEY\)/)
  assert.match(preferenceSource, /storage\.get\(TOGGLE_COLOR\)/)
  assert.match(preferenceSource, /storage\.set\(THEME_COLOR_STORAGE_KEY, nextColor\)/)
  assert.match(preferenceSource, /storage\.set\(TOGGLE_COLOR, nextColor\)/)
})

test('startup restores every valid saved palette color instead of rewriting cyan', () => {
  assert.match(bootstrapSource, /getStoredThemeColor\(defaultSettings\.primaryColor\)/)
  assert.doesNotMatch(bootstrapSource, /legacyDefaultColor/)
  assert.match(appStoreSource, /color: getStoredThemeColor\(DEFAULT_PRIMARY_COLOR\)/)
  assert.match(appStoreSource, /state\.color = persistThemeColor\(color, DEFAULT_PRIMARY_COLOR\)/)
})

test('saved theme color is applied once by the layout in production and during loading', () => {
  assert.match(layoutSource, /updateTheme\(val, this\.isInitialThemeColorLoad\)/)
  assert.doesNotMatch(layoutSource, /process\.env\.NODE_ENV !== 'production'[\s\S]{0,160}updateTheme\(val/)
  assert.doesNotMatch(drawerSource, /updateTheme\(this\.currentPrimaryColor, true\)/)
  assert.doesNotMatch(drawerSource, /updateTheme\(color\)/)
  assert.match(indexSource, /getItem\('qd-ui-primary-color'\) \|\| window\.localStorage\.getItem\('color'\)/)
})
