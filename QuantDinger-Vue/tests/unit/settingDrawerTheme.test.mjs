import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const componentPath = fileURLToPath(
  new URL('../../src/components/SettingDrawer/SettingDrawer.vue', import.meta.url)
)
const source = fs.readFileSync(componentPath, 'utf8')

test('dark setting drawer uses the app black surface from its own theme state', () => {
  assert.match(source, /:class="\{ 'setting-drawer--dark': isDarkDrawer \}"/)
  assert.match(source, /&\.setting-drawer--dark \{[\s\S]*?background: #080808 !important;/)
  assert.match(source, /--setting-drawer-bg: #080808;/)
  assert.match(source, /--setting-drawer-panel: #111111;/)
  assert.doesNotMatch(source, /--setting-drawer-bg: #11161c;/)
  assert.doesNotMatch(source, /background: #171717 !important;/)
})
