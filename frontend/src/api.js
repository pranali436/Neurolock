import { supabase } from './supabase'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const BIOMETRIC_TOKEN_KEY = 'neurolock:biometric-token'
const BIOMETRIC_SCORE_KEY = 'neurolock:biometric-accuracy'

// The second-factor token is a short-lived, server-signed value. It is kept in
// memory and mirrored to sessionStorage so a page reload within the same tab
// does not lose it. It is only ever sent as proof; the server independently
// validates its signature, expiry and user binding.
let biometricToken = null
try {
  biometricToken = window.sessionStorage.getItem(BIOMETRIC_TOKEN_KEY)
} catch {
  biometricToken = null
}

// The accuracy score returned by the server for this session's real
// verification. It is shown only inside the protected dashboard; it is never
// invented client-side. Cleared whenever the second-factor token is cleared.
let biometricScore = null
try {
  const raw = window.sessionStorage.getItem(BIOMETRIC_SCORE_KEY)
  biometricScore = raw === null ? null : Number(raw)
  if (!Number.isFinite(biometricScore)) biometricScore = null
} catch {
  biometricScore = null
}

export function getBiometricToken() {
  return biometricToken
}

export function setBiometricToken(token) {
  biometricToken = token || null
  try {
    if (biometricToken) window.sessionStorage.setItem(BIOMETRIC_TOKEN_KEY, biometricToken)
    else window.sessionStorage.removeItem(BIOMETRIC_TOKEN_KEY)
  } catch {
    /* storage unavailable; token still lives in memory for this page */
  }
}

export function getBiometricScore() {
  return biometricScore
}

export function setBiometricScore(value) {
  const next = Number(value)
  biometricScore = Number.isFinite(next) ? next : null
  try {
    if (biometricScore === null) window.sessionStorage.removeItem(BIOMETRIC_SCORE_KEY)
    else window.sessionStorage.setItem(BIOMETRIC_SCORE_KEY, String(biometricScore))
  } catch {
    /* storage unavailable; score still lives in memory for this page */
  }
}

export function clearBiometricToken() {
  setBiometricToken(null)
  setBiometricScore(null)
}

export async function api(path, options = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Please sign in to continue.')
  const headers = { Authorization: `Bearer ${token}`, ...(options.headers || {}) }
  if (biometricToken) headers['X-Biometric-Token'] = biometricToken
  let response
  try {
    response = await fetch(`${API}${path}`, { ...options, headers })
  } catch (cause) {
    const error = new Error('Could not reach the NeuroLock server. Check your connection and try again.')
    error.isNetworkError = true
    error.cause = cause
    throw error
  }
  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = result.detail
    const message = typeof detail === 'string' ? detail : (detail && detail.message) || result.message || 'Request failed.'
    const error = new Error(message)
    error.status = response.status
    error.code = (detail && typeof detail === 'object' && detail.code) || result.code
    error.payload = result
    if (error.status === 403 && error.code === 'biometric_required') {
      // The step-up is missing or expired: drop the stale token and let the app
      // route the user back to verification.
      clearBiometricToken()
      try { window.dispatchEvent(new CustomEvent('neurolock:biometric-required')) } catch { /* no window */ }
    }
    throw error
  }
  return result
}

export function fileApi(path, options = {}) {
  return api(path, options)
}
