<template>
  <span
    class="brand-identity"
    :class="[
      `brand-identity--${isDark ? 'dark' : 'light'}`,
      { 'brand-identity--compact': compact }
    ]"
    role="img"
    :aria-label="name"
  >
    <span
      v-if="resolvedWideLogo"
      class="brand-identity__wide-shell"
      :class="{ 'brand-identity__wide-shell--bundled': !wideLogo }"
    >
      <img
        :src="resolvedWideLogo"
        class="brand-identity__wide brand-identity__wide--base"
        alt=""
      >
      <img
        v-if="isDark && !wideLogo"
        :src="resolvedWideLogo"
        class="brand-identity__wide brand-identity__wide--dark-wordmark"
        alt=""
        aria-hidden="true"
      >
    </span>
    <img
      v-else
      :src="resolvedMark"
      class="brand-identity__mark"
      :class="{ 'brand-identity__mark--bundled': !resolvedCompactLogo }"
      alt=""
    >
  </span>
</template>

<script>
import bundledWideLogo from '@/assets/logo.png'
import bundledMark from '@/assets/slogo.png'

export default {
  name: 'BrandIdentity',
  props: {
    name: {
      type: String,
      required: true
    },
    theme: {
      type: String,
      default: 'light'
    },
    compact: {
      type: Boolean,
      default: false
    },
    wideLogo: {
      type: String,
      default: ''
    },
    compactLogo: {
      type: String,
      default: ''
    }
  },
  computed: {
    isDark () {
      return this.theme === 'dark' || this.theme === 'realdark'
    },
    resolvedWideLogo () {
      return this.compact ? '' : (this.wideLogo || bundledWideLogo)
    },
    resolvedCompactLogo () {
      return this.compact ? this.compactLogo : ''
    },
    resolvedMark () {
      return this.resolvedCompactLogo || bundledMark
    }
  }
}
</script>

<style lang="less" scoped>
.brand-identity {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  height: 100%;
  gap: 8px;
  color: #111827;
  white-space: nowrap;
}

.brand-identity--dark {
  color: #f8fafc;
}

.brand-identity--compact {
  justify-content: center;
  width: 100%;
  gap: 0;
}

.brand-identity__mark {
  display: block;
  flex: 0 0 auto;
  width: 32px !important;
  height: 32px !important;
  max-width: 32px !important;
  max-height: 32px !important;
  object-fit: contain;
}

.brand-identity--compact .brand-identity__mark {
  width: 32px !important;
  height: 32px !important;
  max-width: 32px !important;
  max-height: 32px !important;
}

.brand-identity--light .brand-identity__mark--bundled {
  filter: drop-shadow(0 0 0.8px rgba(15, 23, 42, 0.82));
}

.brand-identity--dark .brand-identity__mark--bundled {
  filter: drop-shadow(0 0 0.8px rgba(255, 255, 255, 0.78));
}

.brand-identity__wide {
  display: block;
  width: auto !important;
  height: auto !important;
  max-width: 100% !important;
  max-height: 30px !important;
  object-fit: contain;
}

.brand-identity__wide-shell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  max-width: 100%;
}

.brand-identity--dark .brand-identity__wide-shell--bundled .brand-identity__wide--base {
  filter: drop-shadow(0 0 0.7px rgba(255, 255, 255, 0.92));
}

.brand-identity__wide--dark-wordmark {
  position: absolute;
  inset: 0;
  clip-path: inset(0 0 0 19%);
  filter: brightness(0) invert(1);
  pointer-events: none;
}
</style>
