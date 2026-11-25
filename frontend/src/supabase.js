import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY

console.log('Supabase URL loaded:', url)
console.log('Supabase public key loaded:', Boolean(key))

// Supabase Auth uses the implicit flow by default, so email links
// (confirmation, recovery, magic link) land on the app with tokens in the URL
// hash or with an authorization code / token hash / error in the URL. Capture
// these synchronously, before the client processes and clears the URL.
function readAuthParams() {
  if (typeof window === 'undefined') {
    return { type: null, hasCode: false, tokenHash: null, errorCode: null, errorDescription: null }
  }
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const search = new URLSearchParams(window.location.search)
  const pick = (name) => search.get(name) ?? hash.get(name)
  return {
    type: pick('type'),
    hasCode: search.has('code') || hash.has('code'),
    tokenHash: pick('token_hash'),
    errorCode: pick('error_code') || pick('error'),
    errorDescription: pick('error_description'),
  }
}

export const authParams = readAuthParams()

// Confirmation redirects carry type=signup (email confirm) or type=email /
// email_change. Recovery redirects carry type=recovery and are handled by the
// password-reset route instead.
export const isEmailConfirmationRedirect = ['signup', 'email', 'email_change'].includes(authParams.type)

const RECOVERY_FLAG = 'neurolock:password-recovery'

function detectRecoveryRedirect() {
  if (typeof window === 'undefined') return false
  if (authParams.type === 'recovery') {
    try { window.sessionStorage.setItem(RECOVERY_FLAG, '1') } catch { /* storage unavailable */ }
    return true
  }
  try { return window.sessionStorage.getItem(RECOVERY_FLAG) === '1' } catch { return false }
}

export const recoveryRedirect = detectRecoveryRedirect()

export function clearRecoveryRedirect() {
  try { window.sessionStorage.removeItem(RECOVERY_FLAG) } catch { /* storage unavailable */ }
}

export const supabase = createClient(
  url || 'https://example.supabase.co',
  key || 'missing-key'
)
