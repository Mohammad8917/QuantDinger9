/**
 * Portfolio monitor API.
 */
import request from '@/utils/request'

export function getMonitors () {
  return request({
    url: '/api/portfolio/monitors',
    method: 'get'
  })
}

export function addMonitor (data) {
  return request({
    url: '/api/portfolio/monitors',
    method: 'post',
    data
  })
}

export function updateMonitor (id, data) {
  return request({
    url: `/api/portfolio/monitors/${id}`,
    method: 'put',
    data
  })
}

export function deleteMonitor (id) {
  return request({
    url: `/api/portfolio/monitors/${id}`,
    method: 'delete'
  })
}
