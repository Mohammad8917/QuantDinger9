/**
 * Global Market Dashboard API
 */
import request from '@/utils/request'

const BASE_URL = '/api/global-market'

/**
 * Get economic calendar with impact indicators
 */
export function getEconomicCalendar (params = {}) {
  return request({
    url: `${BASE_URL}/calendar`,
    method: 'get',
    params
  })
}
