import axios from 'axios'

const request = axios.create({ baseURL: '/api', timeout: 10000 })

request.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(normalize(error))
)

function normalize(error) {
  return {
    message: (error && error.message) || 'unknown error',
    status: (error && error.response && error.response.status) || 0
  }
}

export default request
