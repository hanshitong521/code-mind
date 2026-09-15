export function formatDate(value) {
  if (!value) {
    return ''
  }
  return value.slice(0, 10)
}

export function formatMoney(cents) {
  const units = cents / 100
  return units.toFixed(2)
}
