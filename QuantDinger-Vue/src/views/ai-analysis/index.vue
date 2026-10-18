<template>
  <div
    class="professional-analysis-page qd-workspace-page"
    :class="{ 'theme-dark': isDarkTheme, embedded }"
    :style="{ '--primary-color': primaryColor }"
  >
    <CopilotWorkbench />
  </div>
</template>

<script>
import { mapState } from 'vuex'
import CopilotWorkbench from './components/CopilotWorkbench.vue'

export default {
  name: 'ProfessionalAnalysisPage',
  components: { CopilotWorkbench },
  props: {
    embedded: { type: Boolean, default: false }
  },
  computed: {
    ...mapState({
      navTheme: state => state.app.theme,
      primaryColor: state => state.app.color || 'var(--primary-color, #1890ff)'
    }),
    isDarkTheme () {
      return this.navTheme === 'dark' || this.navTheme === 'realdark'
    }
  }
}
</script>

<style scoped>
.professional-analysis-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #eef3f8;
}

.professional-analysis-page.embedded {
  height: 100%;
  background: transparent;
}

.professional-analysis-page.theme-dark {
  background: #0a0a0a;
}

</style>
