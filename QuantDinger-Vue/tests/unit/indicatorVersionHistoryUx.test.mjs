import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../../src/views/indicator-ide/index.vue', import.meta.url), 'utf8')

test('indicator version preview opens in a modal instead of below the history list', () => {
  const drawerStart = source.indexOf('<a-drawer\n      :title="$t(\'indicatorIde.codeVersionHistory\')"')
  const drawerEnd = source.indexOf('</a-drawer>', drawerStart)
  const modalStart = source.indexOf('<a-modal\n      :visible="!!codeVersionPreview"')

  assert.ok(drawerStart >= 0)
  assert.ok(drawerEnd > drawerStart)
  assert.ok(modalStart > drawerEnd)
  assert.doesNotMatch(source.slice(drawerStart, drawerEnd), /class="code-version-preview"/)
  assert.match(source, /indicator-version-preview-modal/)
})

test('indicator version preview exposes request progress and ignores stale responses', () => {
  assert.match(source, /:loading="previewingCodeVersionId === item\.id"/)
  assert.match(source, /this\.previewingCodeVersionId = item\.id/)
  assert.match(source, /if \(this\.previewingCodeVersionId !== item\.id\) return/)
})

test('indicator version preview renders a responsive code viewer with stable line numbers', () => {
  assert.match(source, /codeVersionPreviewLines \(\)/)
  assert.match(source, /v-for="\(line, index\) in codeVersionPreviewLines"/)
  assert.match(source, /class="code-version-viewer__number"/)
  assert.match(source, /\.code-version-viewer \{[\s\S]*?overflow: auto;[\s\S]*?scrollbar-width: thin;/)
})
