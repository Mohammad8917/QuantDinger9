import { constantRouterMap } from '@/config/router.config'
import { generatorDynamicRouter } from '@/router/generator-routers'

const permission = {
  state: {
    routers: constantRouterMap,
    addRouters: []
  },
  mutations: {
    SET_ROUTERS: (state, routers) => {
      state.addRouters = routers
      state.routers = constantRouterMap.concat(routers)
    },
    // Reset routers to force regeneration (used on login/logout)
    RESET_ROUTERS: (state) => {
      state.addRouters = []
      state.routers = constantRouterMap
    }
  },
  actions: {
    async GenerateRoutes ({ commit, dispatch }, data) {
      const { token } = data
      const capabilities = await dispatch('LoadFeatureConfig', { force: true }, { root: true })
      const routers = await generatorDynamicRouter(token, capabilities)
      commit('SET_ROUTERS', routers)
    },
    // Reset routes action
    ResetRoutes ({ commit }) {
      commit('RESET_ROUTERS')
    }
  }
}

export default permission
