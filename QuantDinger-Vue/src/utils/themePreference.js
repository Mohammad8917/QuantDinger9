import storage from 'store'
import { TOGGLE_COLOR } from '@/store/mutation-types'

export const THEME_COLOR_STORAGE_KEY = 'qd-ui-primary-color'

const isThemeColor = value => /^#[0-9a-f]{6}$/i.test(String(value || '').trim())

export function normalizeThemeColor (value, fallback) {
  if (isThemeColor(value)) return String(value).trim().toUpperCase()
  if (isThemeColor(fallback)) return String(fallback).trim().toUpperCase()
  return '#52C41A'
}

export function getStoredThemeColor (fallback) {
  const savedColor = storage.get(THEME_COLOR_STORAGE_KEY)
  if (isThemeColor(savedColor)) return normalizeThemeColor(savedColor, fallback)

  const legacyColor = storage.get(TOGGLE_COLOR)
  return normalizeThemeColor(legacyColor, fallback)
}

export function persistThemeColor (color, fallback) {
  const nextColor = normalizeThemeColor(color, fallback)
  storage.set(THEME_COLOR_STORAGE_KEY, nextColor)
  storage.set(TOGGLE_COLOR, nextColor)
  return nextColor
}
