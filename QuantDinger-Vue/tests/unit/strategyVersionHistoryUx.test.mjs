import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../../src/views/strategy-ide/index.vue', import.meta.url), 'utf8')

test('strategy version preview opens in a modal instead of below the full history list', () => {
  const drawerStart = source.indexOf('<a-drawer\n      :visible="showVersionDrawer"')
  const drawerEnd = source.indexOf('</a-drawer>', drawerStart)
  const modalStart = source.indexOf('<a-modal\n      :visible="!!scriptVersionPreview"')

  assert.ok(drawerStart >= 0)
  assert.ok(drawerEnd > drawerStart)
  assert.ok(modalStart > drawerEnd)
  assert.doesNotMatch(source.slice(drawerStart, drawerEnd), /class="code-version-preview"/)
  assert.match(source, /script-version-preview-modal/)
})

test('strategy version preview exposes request progress and ignores stale responses', () => {
  assert.match(source, /:loading="previewingScriptVersionId === item\.id"/)
  assert.match(source, /this\.previewingScriptVersionId = item\.id/)
  assert.match(source, /if \(this\.previewingScriptVersionId !== item\.id\) return/)
})

test('strategy version preview renders a responsive code viewer with stable line numbers', () => {
  assert.match(source, /scriptVersionPreviewLines \(\)/)
  assert.match(source, /v-for="\(line, index\) in scriptVersionPreviewLines"/)
  assert.match(source, /class="code-version-viewer__number"/)
  assert.match(source, /\.code-version-viewer \{[\s\S]*?overflow: auto;[\s\S]*?scrollbar-width: thin;/)
})
