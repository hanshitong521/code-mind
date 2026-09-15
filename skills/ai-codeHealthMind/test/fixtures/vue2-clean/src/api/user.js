import request from '@/utils/request'

export function fetchUser(id) {
  return request({
    url: '/user/' + id,
    method: 'get'
  }).then((res) => normalizeUser(res))
}

function normalizeUser(raw) {
  return { id: raw.id, name: raw.name || 'anonymous' }
}
