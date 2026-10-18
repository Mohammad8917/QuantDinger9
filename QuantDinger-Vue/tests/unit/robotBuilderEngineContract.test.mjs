import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const builderPath = fileURLToPath(
  new URL('../../src/views/executor-strategies/index.vue', import.meta.url)
)
const strategyIdePath = fileURLToPath(
  new URL('../../src/views/strategy-ide/index.vue', import.meta.url)
)
const robotBuilderLocalePath = fileURLToPath(
  new URL('../../src/locales/lang/robot-builder-overrides.js', import.meta.url)
)
const builderSource = fs.readFileSync(builderPath, 'utf8')
const strategyIdeSource = fs.readFileSync(strategyIdePath, 'utf8')
const robotBuilderLocaleSource = fs.readFileSync(robotBuilderLocalePath, 'utf8')

test('embedded robot builder keeps the workspace focused on template inputs and preview', () => {
  assert.doesNotMatch(builderSource, /data-testid="robot-builder-progress"/)
  assert.doesNotMatch(builderSource, /data-testid="robot-engine-compatibility"/)
  assert.doesNotMatch(builderSource, /class="executor-notes"/)
  assert.match(builderSource, /v-model="form\.dynamic_anchor"/)
  assert.match(builderSource, /executorStrategies\.dynamicAnchorHint/)
})

test('robot generation remains visible and requires a valid engine payload', () => {
  assert.match(builderSource, /class="config-actions__status"/)
  assert.match(builderSource, /:disabled="!canCreate"/)
  assert.match(builderSource, /validationIssues \(\) \{/)
  assert.match(builderSource, /const hasLiveCredential = this\.embedded \|\| this\.form\.execution_mode !== 'live'/)
  assert.match(builderSource, /if \(!this\.embedded && this\.form\.execution_mode === 'live' && !this\.selectedCredential\)/)
  assert.match(builderSource, /value="neutral"[\s\S]*?disabled/)
  assert.match(builderSource, /\.is-embedded \.executor-workbench \{[\s\S]*?height: 100%/)
})

test('robot configuration keeps high-frequency choices in compact horizontal controls', () => {
  assert.match(builderSource, /class="market-compact-grid"/)
  assert.match(builderSource, /v-model="form\.side" class="compact-segmented"/)
  assert.match(builderSource, /v-model="form\.market_type"[\s\S]*?class="compact-segmented"/)
  assert.match(builderSource, /v-model="form\.grid_mode" class="compact-segmented"/)
  assert.match(builderSource, /\.compact-segmented[\s\S]*?display: flex[\s\S]*?flex-wrap: nowrap/)
  assert.match(builderSource, /grid-template-columns: minmax\(430px, 480px\) minmax\(0, 1fr\)/)
})

test('embedded robot types reset to the top with advanced settings closed', () => {
  assert.match(builderSource, /ref="configScroll" class="executor-config-scroll"/)
  assert.match(builderSource, /advancedKeys: this\.embedded \? \[\] : \['advanced'\]/)
  assert.match(builderSource, /if \(this\.embedded\) this\.advancedKeys = \[\]/)
  assert.match(builderSource, /this\.\$refs\.configScroll\.scrollTop = 0/)
  assert.match(builderSource, /ref="previewPanel" class="executor-preview-panel"/)
  assert.match(builderSource, /querySelectorAll\('\.ant-table-body'\)/)
  assert.match(builderSource, /element\.scrollLeft = 0/)
  assert.match(builderSource, /v-model="advancedKeys" class="advanced-collapse"/)
})

test('embedded advanced settings render as one bordered disclosure surface', () => {
  assert.match(builderSource, /\.is-embedded \.advanced-collapse\s*\{[^}]*border:\s*1px solid #e5e7eb;[^}]*border-radius:\s*8px;[^}]*overflow:\s*hidden;/s)
  assert.match(builderSource, /\.is-embedded \.advanced-collapse \/deep\/ \.ant-collapse-content\s*\{[^}]*border-top:\s*1px solid #e5e7eb;/s)
  assert.match(builderSource, /\.theme-dark\.is-embedded \.advanced-collapse \/deep\/ \.ant-collapse-content\s*\{[^}]*border-color:\s*#2a2a2a;/s)
})

test('embedded robot catalog uses compact theme-aware icons', () => {
  assert.match(builderSource, /<span class="catalog-icon"><a-icon :type="item\.icon" \/><\/span>/)
  assert.match(builderSource, /\.is-embedded \.catalog-icon \{[\s\S]*?color: var\(--primary-color[\s\S]*?background: color-mix/)
  assert.doesNotMatch(builderSource, /v-if="!embedded" class="catalog-icon"/)
})

test('embedded preview table only scrolls vertically when rows exceed the compact viewport', () => {
  assert.match(builderSource, /:scroll="tableScroll"/)
  assert.match(builderSource, /tableScroll \(\) \{[\s\S]*?if \(!this\.embedded\) return \{ x: 860, y: 430 \}[\s\S]*?this\.levels\.length > 8 \? \{ y: 430 \} : undefined/)
  assert.match(builderSource, /const width = \(compact, regular\) => this\.embedded \? compact : regular/)
  assert.match(builderSource, /this\.form\.executor_type === 'layered_martingale'[\s\S]*?column\.dataIndex !== 'level'[\s\S]*?rows\.filter\(column => !\['layer_index', 'order_index'\]\.includes\(column\.dataIndex\)\)/)
  assert.match(builderSource, /\.is-embedded \.executor-level-table \/deep\/ \.ant-table-body::\-webkit-scrollbar \{[\s\S]*?height: 6px/)
})

test('robot risk surfaces use a neutral visual treatment', () => {
  assert.match(builderSource, /\.theme-dark \.equity-risk-card \{[\s\S]*?background: #171717/)
  assert.match(builderSource, /\.theme-dark \.trigger-contract-card \{[\s\S]*?background: #171717/)
  assert.doesNotMatch(builderSource, /\.theme-dark \.equity-risk-card \{[\s\S]*?background: #102a43/)
})

test('robot builder accents follow the active system theme', () => {
  assert.match(builderSource, /\.panel-step \{[\s\S]*?background: var\(--primary-color/)
  assert.match(builderSource, /\.catalog-item\.active \{[\s\S]*?border-color: var\(--primary-color/)
  assert.match(builderSource, /class="theme-accent-tag"/)
  assert.doesNotMatch(builderSource, /#52c41a|#389e0d|#73d13d|#b7eb8f|#f6ffed/)
})

test('generated robot metadata is preserved for save, backtest and live deployment', () => {
  assert.match(strategyIdeSource, /this\.scriptTemplateKey = generated\.template_key \|\| ''/)
  assert.match(strategyIdeSource, /robot_compatibility: generated\.compatibility \|\| \{\}/)
  assert.match(strategyIdeSource, /generated\.trading_config && generated\.trading_config\.executor_config/)
  assert.match(strategyIdeSource, /delete generatedTradingConfig\.initial_capital/)
  assert.match(strategyIdeSource, /delete generatedTradingConfig\.leverage/)
})

test('template configuration excludes run capital and leverage', () => {
  assert.doesNotMatch(builderSource, /v-model="form\.initial_capital"/)
  assert.doesNotMatch(builderSource, /v-model="form\.leverage"/)
  assert.match(builderSource, /delete templateConfig\.initial_capital/)
  assert.match(builderSource, /delete templateConfig\.leverage/)
  assert.match(builderSource, /fmtWeight \(value\)/)
})

test('grid open-order input supports the complete 200-cell safety limit', () => {
  assert.match(builderSource, /v-model="form\.max_open_orders"[\s\S]*?:max="200"[\s\S]*?@change="normalizeMaxOpenOrders"/)
  assert.match(builderSource, /normalizeMaxOpenOrders \(value\) \{[\s\S]*?Math\.min\(200, Math\.max\(1, Math\.trunc\(parsed\)\)\)/)
})

test('grid preview warning codes are localized instead of leaking internal identifiers', () => {
  assert.match(robotBuilderLocaleSource, /executorStrategies\.warning\.max_open_orders_adjusted_to_grid_count/)
  assert.match(robotBuilderLocaleSource, /executorStrategies\.warning\.high_frequency_grid_backtest_workload/)
  assert.match(builderSource, /previewWarnings\.join\(' · '\)/)
})

test('standalone robot creation defaults to live execution and shows it first', () => {
  assert.match(builderSource, /execution_mode: 'live'/)
  assert.match(builderSource, /value="live"[\s\S]*value="signal"/)
  assert.match(builderSource, /if \(this\.embedded\)[\s\S]*execution_mode: 'signal'/)
})
