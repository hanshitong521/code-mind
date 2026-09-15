import request from '@/utils/request'

export function fetchOrders() {
  return request({
    url: '/orders',
    method: 'get'
  }).then((res) => res.items)
}
