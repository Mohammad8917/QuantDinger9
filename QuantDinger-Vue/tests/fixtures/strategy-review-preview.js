import Vue from 'vue'
import VueI18n from 'vue-i18n'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Review from '../../src/views/strategy-center/components/StrategyReviewReport.vue'
import messages from '../../src/locales/lang/strategy-review.js'
import { report } from './strategy-review-api.js'

Vue.use(VueI18n)
Vue.use(Antd)
const options = new URLSearchParams(location.search)
const dark = options.get('theme') !== 'light'
document.body.style.cssText = `margin:0;padding:28px;background:${dark ? '#181a1e' : '#ffffff'};--primary-color:#52c41a;`
new Vue({
  i18n: new VueI18n({ locale: options.get('lang') || 'zh-CN', fallbackLocale: 'en-US', messages }),
  render: h => h(Review, { ref: 'review', props: { strategyId: 1, isDark: dark } }),
  mounted () {
    this.$refs.review.report = report
    if (options.get('width')) this.$el.style.width = options.get('width') + 'px'
  }
}).$mount('#app')
