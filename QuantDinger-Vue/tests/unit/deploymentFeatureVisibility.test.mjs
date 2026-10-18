import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const read = relativePath => fs.readFileSync(path.join(root, relativePath), 'utf8')

test('deployment capabilities control navigation and monetization surfaces', () => {
  const routes = read('src/config/router.config.js')
  const routeFilter = read('src/router/generator-routers.js')
  const accountHeader = read('src/components/GlobalHeader/AvatarDropdown.vue')
  const profile = read('src/views/profile/index.vue')
  const indicatorIde = read('src/views/indicator-ide/index.vue')
  const strategyIde = read('src/views/strategy-ide/index.vue')
  const userManage = read('src/views/user-manage/index.vue')
  const featureStore = read('src/store/modules/features.js')

  assert.match(routes, /capability: 'marketplace_enabled'/)
  assert.match(routes, /capability: 'billing_enabled'/)
  assert.match(routeFilter, /capabilities\[requiredCapability\] === false/)
  assert.match(accountHeader, /v-if="billingEnabled"/)
  assert.match(profile, /v-if="billingEnabled" key="credits"/)
  assert.match(profile, /v-if="billingEnabled" key="referrals"/)
  assert.match(indicatorIde, /<button v-if="marketplaceEnabled" type="button" class="ide-indicator-market-entry"/)
  assert.match(indicatorIde, /\.ide-indicator-market-entry[\s\S]*?var\(--primary-color/)
  assert.match(strategyIde, /currentSourceId && marketplaceEnabled/)
  assert.match(userManage, /v-if="billingEnabled" key="orders"/)
  assert.match(userManage, /v-if="billingEnabled" key="rewardWithdrawals"/)
  assert.match(featureStore, /billing_enabled: false/)
  assert.match(featureStore, /marketplace_enabled: false/)
})

test('settings feature switch copy is available in every supported locale', () => {
  const source = read('src/locales/settings-feature-overrides.js')
  for (const locale of ['en-US', 'zh-CN', 'zh-TW', 'ja-JP', 'ko-KR', 'de-DE', 'fr-FR', 'ru-RU', 'th-TH', 'vi-VN', 'ar-SA']) {
    assert.match(source, new RegExp(`'${locale}'`))
  }
})
