import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ShieldCheck, LockKeyhole, Fingerprint, FileLock2, ArrowRight, UploadCloud, FileText, LogOut, LayoutDashboard, CheckCircle2, AlertCircle, Trash2, Download, Mail, Menu, X, Eye, EyeOff } from 'lucide-react'
import { supabase, recoveryRedirect, clearRecoveryRedirect, authParams, isEmailConfirmationRedirect } from './supabase'
import { api, setBiometricToken, clearBiometricToken, getBiometricScore, setBiometricScore } from './api'
import { TYPING_SAMPLES } from './typingSamples'
import TypingAnalysis from './TypingAnalysis'
const MIN_DWELL_SAMPLES = 10

// Server-verified second-factor state. The frontend never decides this itself
// (no client boolean/percentage): it asks /api/auth/status, which validates the
// signed token the server issued after a passing biometric check.
function useBiometric(session) {
  const userId = session?.user?.id || null
  const [state, setState] = useState({ loading: Boolean(session), verified: false, expiresIn: null, checkedFor: null })
  const refresh = useCallback(async () => {
    if (!userId) { setState({ loading: false, verified: false, expiresIn: null, checkedFor: null }); return false }
    setState(s => ({ ...s, loading: true }))
    try {
      const result = await api('/api/auth/status')
      const verified = Boolean(result.biometric_verified)
      setState({ loading: false, verified, expiresIn: result.expires_in_seconds ?? null, checkedFor: userId })
      return verified
    } catch (e) {
      setState({ loading: false, verified: false, expiresIn: null, error: e.message, checkedFor: userId })
      return false
    }
  }, [userId])
  useEffect(()=>{ refresh() }, [refresh])
  // A session is "loading" until its status has been checked at least once.
  // Without this, the dashboard guard can evaluate verified=false before the
  // async /api/auth/status call returns and bounce a valid user to /verify.
  const loading = state.loading || (Boolean(userId) && state.checkedFor !== userId)
  return { ...state, loading, refresh }
}

// Derive the timing features the backend expects. Only numbers are produced;
// the typed text itself is never included, sent or stored.
function computeTypingFeatures(dwells, flights) {
  const mean = arr => arr.reduce((a,b)=>a+b,0)/(arr.length||1)
  const variance = arr => { const m = mean(arr); return mean(arr.map(x=>(x-m)**2)) }
  return {
    mean_dwell: mean(dwells),
    mean_flight: mean(flights),
    std_flight: Math.sqrt(variance(flights)),
    count: dwells.length,
  }
}

function useSession() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [recovery, setRecovery] = useState(recoveryRedirect)
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false) })
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      if (event === 'PASSWORD_RECOVERY') setRecovery(true)
      setSession(next)
    })
    return () => data.subscription.unsubscribe()
  }, [])
  return { session, loading, recovery }
}

function PasswordInput({ label, value, onChange, autoComplete, minLength, placeholder, required = true }) {
  const [visible, setVisible] = useState(false)
  return <label>{label}<span className="password-field"><input type={visible ? 'text' : 'password'} autoComplete={autoComplete} minLength={minLength} value={value} onChange={onChange} placeholder={placeholder} required={required}/><button type="button" className="password-toggle" onClick={() => setVisible(v => !v)} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} title={visible ? 'Hide password' : 'Show password'}>{visible ? <EyeOff size={17} aria-hidden="true"/> : <Eye size={17} aria-hidden="true"/>}</button></span></label>
}

function Layout({ children, session }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  async function logout() { clearBiometricToken(); await supabase.auth.signOut(); navigate('/') }
  return <div className="app-shell">
    <header className="topbar">
      <Link className="brand" to="/"><span className="brand-mark"><ShieldCheck size={22}/></span><span>Neuro<span className="brand-blue">Lock</span><small>BEHAVIORAL SECURITY</small></span></Link>
      <button className="mobile-toggle" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle menu">{mobileOpen ? <X/> : <Menu/>}</button>
      <nav className={mobileOpen ? 'nav nav-open' : 'nav'}>
        {session ? <><NavLink to="/dashboard" onClick={() => setMobileOpen(false)}>Dashboard</NavLink><NavLink to="/typing-analysis" onClick={() => setMobileOpen(false)}>Typing analysis</NavLink><button className="nav-signout" onClick={logout}><LogOut size={16}/> Sign out</button></> :
          <><NavLink to="/#features" onClick={() => setMobileOpen(false)}>Features</NavLink><Link className="nav-login" to="/login" onClick={() => setMobileOpen(false)}>Sign in</Link><Link className="button button-small" to="/register" onClick={() => setMobileOpen(false)}>Get started <ArrowRight size={15}/></Link></>}
      </nav>
    </header>
    <main>{children}</main>
    <footer className="footer"><Link className="brand brand-footer" to="/"><span className="brand-mark"><ShieldCheck size={18}/></span><span>Neuro<span className="brand-blue">Lock</span></span></Link><span>Behavioral security, designed around you.</span><span>Prototype â€¢ Do not use for critical data</span></footer>
  </div>
}

function Home() {
  return <><section className="hero wrap">
    <div className="hero-copy"><div className="eyebrow"><span className="pulse-dot"/> A smarter layer of file protection</div>
      <h1>Your typing is<br/><span className="gradient-text">uniquely yours.</span></h1>
      <p className="hero-lead">NeuroLock adds behavioral biometrics to your secure workspace, helping protect your files with the rhythm of the way you type.</p>
      <div className="hero-actions"><Link className="button" to="/register">Get started <ArrowRight size={17}/></Link><Link className="button button-ghost" to="/login">I already have an account</Link></div>
      <div className="hero-trust"><span><CheckCircle2 size={16}/> Private file storage</span><span><CheckCircle2 size={16}/> Typing-pattern checks</span></div>
    </div>
    <div className="hero-visual"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="shield-card"><div className="shield-large"><ShieldCheck size={62}/></div><div className="status-pill"><span className="pulse-dot"/> SECURITY LAYER ACTIVE</div><div className="visual-line"><span>Behavioral signal</span><strong>Typing rhythm</strong></div><div className="waveform">{Array.from({length:30},(_,i)=><i key={i} style={{height:`${12+((i*17)%37)}px`}}/>)}</div><div className="visual-line"><span>Storage</span><strong><LockKeyhole size={15}/> Private by default</strong></div></div><div className="floating-chip chip-top"><Fingerprint size={17}/> Identity signals</div><div className="floating-chip chip-bottom"><FileLock2 size={17}/> Protected files</div></div>
  </section>
  <section id="features" className="features-section"><div className="wrap"><div className="section-heading"><div className="eyebrow">BUILT FOR PEACE OF MIND</div><h2>Security that works in layers.</h2><p>One workspace for account access, typing enrollment and private files.</p></div>
    <div className="feature-grid"><Feature icon={<Fingerprint/>} number="01" title="Behavioral enrollment" text="Build a baseline from repeated typing samples, then compare new samples against it."/><Feature icon={<LockKeyhole/>} number="02" title="Private file storage" text="Keep uploaded files in a private storage bucket and request short-lived access links."/><Feature icon={<Mail/>} number="03" title="Security notifications" text="Record important events and optionally send email alerts when configured."/></div>
  </div></section>
  <section className="bottom-cta wrap"><div><div className="eyebrow">YOUR SECURE WORKSPACE</div><h2>Start with a safer space for your files.</h2><p>Create an account, enroll your typing pattern, and open your personal dashboard.</p></div><Link className="button" to="/register">Create your account <ArrowRight size={17}/></Link></section>
  </>
}
function Feature({icon,number,title,text}) { return <article className="feature-card"><div className="feature-top"><span className="feature-icon">{icon}</span><span className="feature-number">{number}</span></div><h3>{title}</h3><p>{text}</p></article> }

function AuthPage({ mode }) {
  const [email,setEmail] = useState('')
  const [password,setPassword] = useState('')
  const [name,setName] = useState('')
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  const location = useLocation()
  useEffect(() => { const notice = location.state?.notice; if (notice) setMessage(notice) }, [location.state])
  const navigate = useNavigate()
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      if (mode === 'register') {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { display_name: name },
            // Must match the /confirm route so the emailed link returns here.
            emailRedirectTo: `${window.location.origin}/confirm`,
          },
        })
        if (error) throw error
        if (data.user && Array.isArray(data.user.identities) && data.user.identities.length === 0) {
          setError('An account with this email already exists. Please sign in with your existing password.')
          return
        }
        if (!data.session) { setMessage('Check your inbox to confirm your email, then sign in.'); return }
        navigate('/typing-analysis')
      } else {
        

const response = await fetch(
  `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/api/login`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }
)

const result = await response.json()

if (!response.ok) {
  throw new Error(result.detail || 'Unable to sign in.')
}

const { error: sessionError } = await supabase.auth.setSession({
  access_token: result.access_token,
  refresh_token: result.refresh_token,
})

if (sessionError) throw sessionError

// A fresh password login clears any old second-factor state. Typing
// verification is no longer part of the sign-in flow.
clearBiometricToken()
navigate('/dashboard')


      }
    } catch(err) { setError(err.message || 'Something went wrong.') }
    finally { setBusy(false) }
  }
  return <section className="auth-layout wrap"><div className="auth-promo"><div className="auth-icon"><ShieldCheck size={32}/></div><div className="eyebrow">WELCOME TO NEUROLOCK</div><h1>{mode==='register'?'Create your secure workspace.':'Welcome back.'}</h1><p>{mode==='register'?'Your account is the first layer. Add your typing pattern and keep your files in a private workspace.':'Sign in to continue to your personal file dashboard and security settings.'}</p><div className="auth-benefit"><CheckCircle2/> Account-based access</div><div className="auth-benefit"><CheckCircle2/> Private storage</div><div className="auth-benefit"><CheckCircle2/> Behavioral verification prototype</div></div>
  <div className="auth-card"><div className="auth-card-head"><h2>{mode==='register'?'Create account':'Sign in'}</h2><p>{mode==='register'?'Enter your details to get started.':'Enter your account details below.'}</p></div>
    <form onSubmit={submit} className="form">
      {mode==='register' && <label>Full name<input autoComplete="name" value={name} onChange={e=>setName(e.target.value)} placeholder="Your name" required/></label>}
      <label>Email address<input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label>
      <PasswordInput label="Password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete={mode==='register'?'new-password':'current-password'} minLength={8} placeholder="At least 8 characters"/>
      {mode==='login' && <div className="auth-helper"><Link to="/forgot-password">Forgot password?</Link></div>}
      {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
      {message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
      <button className="button button-full" disabled={busy}>{busy?'Please waitâ€¦':mode==='register'?'Create account':'Sign in'} <ArrowRight size={17}/></button>
    </form><div className="auth-switch">{mode==='register'?'Already have an account?':'New to NeuroLock?'} <Link to={mode==='register'?'/login':'/register'}>{mode==='register'?'Sign in':'Create an account'}</Link></div>
    <p className="fine-print">Use a unique password. Behavioral matching here is a prototype and is not a substitute for strong authentication.</p>
  </div></section>
}

function ForgotPassword() {
  const [email,setEmail] = useState('')
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const redirectTo = `${window.location.origin}/reset-password`
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo })
      if (error) throw error
      setMessage('If an account exists for that email address, a password reset link is on its way. Check your inbox and spam folder, then open the link to choose a new password.')
    } catch(err) {
      setError(err.message || 'We could not send a reset email right now. Please try again.')
    } finally { setBusy(false) }
  }
  return <section className="auth-layout wrap"><div className="auth-promo"><div className="auth-icon"><ShieldCheck size={32}/></div><div className="eyebrow">ACCOUNT RECOVERY</div><h1>Reset your password.</h1><p>Enter the email address on your account. If it exists, we will email a secure recovery link that verifies your identity before you can set a new password.</p><div className="auth-benefit"><CheckCircle2/> Verified through your email</div><div className="auth-benefit"><CheckCircle2/> No password is ever emailed</div><div className="auth-benefit"><CheckCircle2/> Account lockout stays in place</div></div>
  <div className="auth-card"><div className="auth-card-head"><h2>Forgot password</h2><p>We will send a recovery link to your inbox.</p></div>
    <form onSubmit={submit} className="form">
      <label>Email address<input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label>
      {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
      {message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
      <button className="button button-full" disabled={busy}>{busy?'Sending reset link...':'Send reset link'} <ArrowRight size={17}/></button>
    </form><div className="auth-switch">Remembered your password? <Link to="/login">Sign in</Link></div>
    <p className="fine-print">For your security we show the same confirmation whether or not an account exists for the address you enter.</p>
  </div></section>
}

function ResetPassword({ session, loading, recovery }) {
  const [password,setPassword] = useState('')
  const [confirm,setConfirm] = useState('')
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  async function submit(e) {
    e.preventDefault(); setError(''); setMessage('')
    if (password.length < 8) { setError('Choose a password with at least 8 characters.'); return }
    if (password !== confirm) { setError('The two passwords do not match.'); return }
    setBusy(true)
    try {
      const { error } = await supabase.auth.updateUser({ password })
      if (error) throw error
      setMessage('Your password has been updated. You can now sign in with your new password.')
      clearRecoveryRedirect()
      try { await supabase.auth.signOut() } catch { /* already signed out */ }
    } catch(err) {
      setError(err.message || 'We could not update your password. The recovery link may have expired. Request a new one and try again.')
    } finally { setBusy(false) }
  }
  if (loading) return <div className="loading-screen"><div className="spinner"/><p>Verifying your recovery link...</p></div>
  const ready = Boolean(recovery && session)
  return <section className="auth-layout wrap"><div className="auth-promo"><div className="auth-icon"><LockKeyhole size={32}/></div><div className="eyebrow">ACCOUNT RECOVERY</div><h1>Choose a new password.</h1><p>Your recovery link verified your email address. Set a new password for your NeuroLock account, then sign in again.</p><div className="auth-benefit"><CheckCircle2/> Link verified by email</div><div className="auth-benefit"><CheckCircle2/> Password hidden by default</div><div className="auth-benefit"><CheckCircle2/> Sign in again after updating</div></div>
  <div className="auth-card"><div className="auth-card-head"><h2>Set a new password</h2><p>{ready?'Enter and confirm your new password.':'This recovery session is not active.'}</p></div>
    {message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
    {!message && !ready && <div className="alert alert-error"><AlertCircle size={17}/>This password reset link is invalid or has expired. Please request a new one.</div>}
    {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
    {ready && !message && <form onSubmit={submit} className="form">
      <PasswordInput label="New password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password" minLength={8} placeholder="At least 8 characters"/>
      <PasswordInput label="Confirm new password" value={confirm} onChange={e=>setConfirm(e.target.value)} autoComplete="new-password" minLength={8} placeholder="Re-enter your new password"/>
      <button className="button button-full" disabled={busy}>{busy?'Updating password...':'Update password'} <ArrowRight size={17}/></button>
    </form>}
    {message && <Link className="button button-full" to="/login">Go to sign in <ArrowRight size={17}/></Link>}
    {!ready && !message && <div className="auth-switch"><Link to="/forgot-password">Request a new reset link</Link></div>}
    <p className="fine-print">A password can only be changed after opening the recovery link sent to your account email address, which verifies that you own the inbox.</p>
  </div></section>
}

let emailConfirmationPromise = null

async function handleEmailConfirmation() {
  try {
    if (authParams.errorCode || authParams.errorDescription) {
      return { status: 'error', error: authParams.errorDescription || 'This confirmation link is invalid or has expired.' }
    }

    // Handle the authorization-code (PKCE) form if the project is configured for it.
    if (authParams.hasCode) {
      const code = new URLSearchParams(window.location.search).get('code')
      const { error } = await supabase.auth.exchangeCodeForSession(code)
      if (error) throw error
    } else if (authParams.tokenHash) {
      // Handle the token-hash email template form.
      const { error } = await supabase.auth.verifyOtp({ token_hash: authParams.tokenHash, type: authParams.type || 'signup' })
      if (error) throw error
    }

    // For implicit links (the default) the session is already established by
    // detectSessionInUrl; getSession awaits initialization so it is ready here.
    const { data, error } = await supabase.auth.getSession()
    if (error) throw error
    if (!data.session) {
      return { status: 'error', error: 'This confirmation link is invalid, has expired, or has already been used.' }
    }

    // End the auto-created session so the user signs in normally. This keeps
    // the existing lockout and login-alert flow intact; the email confirmation
    // itself is already recorded by Supabase and is not affected.
    await supabase.auth.signOut()
    return { status: 'success', error: '' }
  } catch (err) {
    return { status: 'error', error: err?.message || 'We could not confirm your email. The link may be invalid or expired.' }
  }
}

function runEmailConfirmation() {
  // Memoize so React StrictMode's double-invoked effects do not process the
  // single-use confirmation token twice. Manual visits still run fresh.
  if (isEmailConfirmationRedirect) {
    if (!emailConfirmationPromise) emailConfirmationPromise = handleEmailConfirmation()
    return emailConfirmationPromise
  }
  return handleEmailConfirmation()
}

function ConfirmEmail() {
  const [status,setStatus] = useState('working')
  const [error,setError] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    let active = true
    runEmailConfirmation().then(result => {
      if (!active) return
      setStatus(result.status)
      setError(result.error || '')
      if (result.status === 'success') {
        setTimeout(() => { if (active) navigate('/login', { replace: true, state: { notice: 'Your email address is confirmed. Please sign in with your password.' } }) }, 1400)
      }
    })
    return () => { active = false }
  }, [navigate])
  return <section className="auth-layout wrap"><div className="auth-promo"><div className="auth-icon"><ShieldCheck size={32}/></div><div className="eyebrow">EMAIL CONFIRMATION</div><h1>{status==='success'?'Your email is confirmed.':status==='error'?'We could not confirm your email.':'Confirming your email...'}</h1><p>{status==='success'?'Your email address is verified. Please sign in to continue to your NeuroLock workspace.':status==='error'?'The confirmation link may be invalid, expired, or already used. Return to sign in to request a new confirmation email.':'Please wait while we verify the link from your email.'}</p><div className="auth-benefit"><CheckCircle2/> Email verification required</div><div className="auth-benefit"><CheckCircle2/> No password is changed</div><div className="auth-benefit"><CheckCircle2/> Sign in normally afterward</div></div>
    <div className="auth-card">
      {status==='working' && <div className="loading-screen"><div className="spinner"/><p>Verifying your confirmation link...</p></div>}
      {status==='success' && <div className="alert alert-success"><CheckCircle2 size={17}/>Your email address has been confirmed. Redirecting you to sign in...</div>}
      {status==='error' && <><div className="alert alert-error"><AlertCircle size={17}/>{error}</div><div className="auth-switch"><Link to="/login">Go to sign in</Link></div></>}
    </div></section>
}

function Verify({ biometric }) {
  const navigate = useNavigate()
  const [value,setValue] = useState('')
  const [capturedSamples,setCapturedSamples] = useState([])
  const [active,setActive] = useState(false)
  const [dwells,setDwells] = useState([])
  const [flights,setFlights] = useState([])
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [result,setResult] = useState(null)
  const [enrolled,setEnrolled] = useState(null)
  const [checking,setChecking] = useState(true)
  const downRef = useRef({})
  const lastKeyUpRef = useRef(0)
  const phraseIndex = Math.min(capturedSamples.length, TYPING_SAMPLES.length - 1)
  const phrase = TYPING_SAMPLES[phraseIndex]

  async function checkEnrollment() {
    setChecking(true); setError('')
    try {
      const status = await api('/api/biometric/status')
      setEnrolled(Boolean(status.enrolled))
    } catch(e) {
      setEnrolled(null)
      setError(e.message || 'Could not check your enrollment status.')
    } finally { setChecking(false) }
  }
  useEffect(()=>{checkEnrollment()},[])

  function begin() {
    setValue(''); setDwells([]); setFlights([]); setError(''); setResult(null)
    downRef.current = {}; lastKeyUpRef.current = 0
    setActive(true)
  }
  function keyDown(e) {
    if (!active || e.repeat || e.key.length !== 1) return
    const now = performance.now()
    downRef.current[e.key] = now
    if (lastKeyUpRef.current) setFlights(prev=>[...prev, Math.max(0, now - lastKeyUpRef.current)])
  }
  function keyUp(e) {
    if (!active || e.key.length !== 1) return
    const now = performance.now()
    const pressedAt = downRef.current[e.key]
    if (pressedAt !== undefined) {
      setDwells(prev=>[...prev, Math.max(0, now - pressedAt)])
      delete downRef.current[e.key]
    }
    lastKeyUpRef.current = now
  }
  async function checkMatch(e) {
    if (e) e.preventDefault()
    setError(''); setResult(null)
    if (value !== phrase) { setError('Please type the exact phrase, including spaces and capitalization.'); return }
    if (dwells.length < MIN_DWELL_SAMPLES) { setError('Not enough timing data was captured. Select “Start typing” and type the phrase again.'); return }
    setActive(false)
    const collected = [...capturedSamples, { features: computeTypingFeatures(dwells, flights) }]
    setCapturedSamples(collected)
    setValue(''); setDwells([]); setFlights([])
    downRef.current = {}; lastKeyUpRef.current = 0
    if (collected.length < TYPING_SAMPLES.length) return
    setBusy(true)
    try {
      const response = await api('/api/biometric/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ samples: collected }),
      })
      setBiometricToken(response.biometric_token)
      setBiometricScore(response.accuracy)
      setResult({ ok: true, message: response.message })
      // Confirm the server-verified session state BEFORE navigating so the
      // dashboard guard cannot read a stale "unverified" value and bounce the
      // user back here. The score shown later comes only from this response.
      const verified = biometric?.refresh ? await biometric.refresh() : true
      if (verified) navigate('/dashboard', { replace: true })
      else setError('Verification succeeded, but we could not confirm your session yet. Please try again.')
    } catch(err) {
      setCapturedSamples([])
      if (err.status === 409) {
        setEnrolled(false)
        setError('You have not enrolled a typing pattern yet. Complete enrollment before verifying.')
      } else if (err.status === 400) {
        setError(err.message || 'The server received insufficient typing data. Type the full phrase and try again.')
      } else if (err.status === 403) {
        // A real mismatch: drop any step-up (and its score) so protected data
        // stays inaccessible, then resync the guard state. The UI shows only a
        // retry message here, never the score or threshold.
        clearBiometricToken()
        if (biometric?.refresh) await biometric.refresh()
        setResult({ ok: false })
      } else if (err.status === 401) {
        setError('Your session is invalid or expired. Please sign in again.')
      } else {
        setError(err.message || 'Verification could not be completed. Please try again.')
      }
    } finally { setBusy(false) }
  }

  const mean = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0
  const bars = dwells.slice(-30)
  const maxDwell = bars.length ? Math.max(...bars, 1) : 1

  return <section className="page wrap"><div className="page-heading"><div className="eyebrow">BEHAVIORAL BIOMETRICS</div><h1>Verify your typing rhythm</h1><p>Type each of the three phrases at your normal pace. NeuroLock measures your key-hold durations and intervals, then compares all three samples with your saved baseline.</p></div>
    {biometric?.verified && <div className="alert alert-success"><CheckCircle2 size={17}/>Second factor active for this session. You can open your dashboard, or run another check below.</div>}
    {checking ? <div className="panel empty-state"><div className="spinner"/><p>Checking your enrollment…</p></div>
      : enrolled !== true ? <div className="panel">
          <div className="side-icon"><Fingerprint size={25}/></div>
          <h3>{enrolled === false ? 'No typing baseline available' : 'Could not check your enrollment'}</h3>
          <p className="muted">{enrolled === false ? 'A typing-rhythm check needs an enrolled baseline first. Create yours on the enrollment page, then come back here.' : 'NeuroLock could not reach the server to confirm whether you have an enrolled typing baseline.'}</p>
          {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
          <div className="panel-links">{enrolled === false && <Link className="button button-small" to="/typing-analysis">Go to typing analysis <ArrowRight size={16}/></Link>}{error && <button type="button" className="text-button" onClick={checkEnrollment}>Retry status check <ArrowRight size={14}/></button>}</div>
        </div>
      : <div className="enroll-grid"><div className="panel">
          <div className="step-line"><span className="step-number">{phraseIndex+1}</span><div><h2>Type Sample {phraseIndex+1}</h2><p>Use your normal pace. Timing is captured only while this field is active.</p></div></div>
          <div className="phrase-box"><span>SAMPLE {phraseIndex+1} — TYPE THIS PHRASE</span><strong>{phrase}</strong><button type="button" className="text-button" onClick={begin} disabled={capturedSamples.length>=TYPING_SAMPLES.length}>{active?'Restart sample':'Start typing'}</button></div>
          <div className="sample-phrases" aria-label="Three sample phrases">
            {TYPING_SAMPLES.map((sample,index)=><p key={sample}><strong>Sample {index+1}{capturedSamples.length>index?' ✓':''}:</strong> {sample}</p>)}
            <p className="muted">{capturedSamples.length} of {TYPING_SAMPLES.length} samples captured. Type all three to verify.</p>
          </div>
          <form onSubmit={checkMatch}><label className="typing-label">Type Sample {phraseIndex+1} here<input value={value} onChange={e=>setValue(e.target.value)} onKeyDown={keyDown} onKeyUp={keyUp} disabled={!active || busy || capturedSamples.length>=TYPING_SAMPLES.length} placeholder={active?'Start typing the phrase…':'Select “Start typing” first'} autoComplete="off" spellCheck="false"/></label><div className="form-row"><span className="muted">{active?'Timing capture active':capturedSamples.length<TYPING_SAMPLES.length?'Timing capture paused':'All samples captured'}</span><button className="button button-small" disabled={!active || busy}>{busy?'Checking…':capturedSamples.length<TYPING_SAMPLES.length-1?'Save sample':'Check match'}</button></div></form>
          {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
          {result && (result.ok
            ? <div className="verify-result success"><div className="verify-result-icon"><CheckCircle2 size={22}/></div><div><h3>Typing pattern matched</h3><span className="muted">Your typing rhythm was confirmed by the server. Opening your dashboard...</span></div></div>
            : <div className="verify-result failure"><div className="verify-result-icon"><AlertCircle size={22}/></div><div><h3>Typing pattern did not match</h3><span className="muted">We could not confirm your typing rhythm, so your dashboard and files stay locked. Select "Try again" and retype all three phrases at your normal pace.</span><button type="button" className="button button-small" onClick={()=>{setCapturedSamples([]);begin()}}>Try again</button></div></div>)}
          <div className="live-capture"><div className="live-capture-head"><span>Live capture</span><strong>{dwells.length} keystrokes timed</strong></div>
            {bars.length ? <div className="waveform live-waveform">{bars.map((d,i)=><i key={i} style={{height:`${Math.max(4, Math.round((d/maxDwell)*45))}px`}} title={`${Math.round(d)} ms hold`}/>)}</div> : <p className="muted">No timing captured yet. Select “Start typing” and type the phrase.</p>}
            <div className="live-metrics"><div><span>Mean hold</span><strong>{dwells.length?`${Math.round(mean(dwells))} ms`:'—'}</strong></div><div><span>Mean interval</span><strong>{flights.length?`${Math.round(mean(flights))} ms`:'—'}</strong></div></div>
            <p className="fine-print">These are measured input values, not a match result. The match decision is made by the NeuroLock server after you choose "Check match".</p>
          </div>
        </div><aside className="panel">
          <div className="side-icon"><Fingerprint size={25}/></div>
          <h3>How verification works</h3>
          <ul className="check-list"><li><CheckCircle2/> Key press (hold) duration</li><li><CheckCircle2/> Time between keystrokes</li><li><CheckCircle2/> Variation in your rhythm</li><li><CheckCircle2/> Compared by the server to your saved baseline</li></ul>
          <div className="privacy-note"><LockKeyhole size={17}/><p>Only derived timing features are sent. The text you type is never sent or stored.</p></div>
          <div className="privacy-note"><ShieldCheck size={17}/><p>Protected resources (your dashboard and files) stay locked until this check passes on the server. The matcher is a prototype and is not production validated.</p></div>
          <Link className="button button-ghost button-full" to="/dashboard">Back to dashboard <ArrowRight size={16}/></Link>
        </aside></div>}
  </section>
}

function Dashboard() {
  const [files,setFiles] = useState([])
  const [loading,setLoading] = useState(true)
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  const [enrolled,setEnrolled] = useState(null)
  // Accuracy from the user's most recent real verification, fetched from the
  // server. Null (shown as "Not available") if they have never completed one.
  const [accuracy,setAccuracy] = useState(null)
  async function refresh() {
    setLoading(true); setError('')
    try {
      const data=await api('/api/files');setFiles(data.files||[])
      try {const status=await api('/api/biometric/status');setEnrolled(Boolean(status.enrolled))} catch {setEnrolled(null)}
      try {const score=await api('/api/biometric/last-score');setAccuracy(typeof score.accuracy==='number'?score.accuracy:null)} catch {setAccuracy(null)}
    }
    catch(e){setError(e.message)}
    finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[])
  async function upload(e) {
    const file=e.target.files?.[0]; if(!file)return
    setBusy(true);setMessage('');setError('')
    try {
      const typingStatus = await api('/api/typing-analysis/status')
      if (!typingStatus.complete) {
        setError('Complete all three typing samples before uploading files. Open the Typing Analysis page to finish the test.')
        return
      }
      const form=new FormData();form.append('file',file);await api('/api/files',{method:'POST',body:form});setMessage(`${file.name} uploaded securely.`);await refresh()
    }
    catch(err){setError(err.message || 'You must finish the typing analysis before uploading files.')}
    finally{setBusy(false);e.target.value=''}
  }
  async function openFile(file) {
    setError('');setMessage('')
    try {const result=await api(`/api/files/${file.id}/signed-url`,{method:'POST'});window.open(result.url,'_blank','noopener,noreferrer')}
    catch(e){setError(e.message)}
  }
  async function removeFile(file) {
    if(!confirm(`Delete ${file.original_name}? This cannot be undone.`))return
    try {await api(`/api/files/${file.id}`,{method:'DELETE'});setFiles(prev=>prev.filter(f=>f.id!==file.id));setMessage('File deleted.')}
    catch(e){setError(e.message)}
  }
  async function alertMe() {
    try {const r=await api('/api/security-alert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event:'Dashboard test alert',detail:'You requested a test security notification from your NeuroLock dashboard.'})});setMessage(r.message)}
    catch(e){setError(e.message)}
  }
  const formatSize = n => n<1024?`${n} B`:n<1024*1024?`${(n/1024).toFixed(1)} KB`:`${(n/(1024*1024)).toFixed(1)} MB`
  return <section className="page wrap"><div className="dashboard-welcome"><div><div className="eyebrow">YOUR PRIVATE WORKSPACE</div><h1>Dashboard</h1><p>Manage your files and review your security setup.</p></div><Link className="button button-small" to="/typing-analysis"><Fingerprint size={17}/> {enrolled?'Review typing test':'Complete typing test'}</Link></div>
    <div className="stat-grid"><div className="stat-card"><span className="stat-icon blue"><FileText/></span><div><span>Stored files</span><strong>{files.length}</strong></div></div><div className="stat-card"><span className="stat-icon green"><ShieldCheck/></span><div><span>Account status</span><strong>Protected</strong></div></div><div className="stat-card"><span className="stat-icon purple"><Fingerprint/></span><div><span>Typing baseline</span><strong>{enrolled===true?'Enrolled':'Check setup'}</strong></div></div><div className="stat-card"><span className="stat-icon purple"><Fingerprint/></span><div><span>Typing Rhythm Accuracy</span><strong>{accuracy==null?'Not available':`${Math.round(accuracy*100)}%`}</strong></div></div></div>
    {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}{message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
    <div className="panel files-panel"><div className="panel-header"><div><h2>Your files</h2><p>Files in your private NeuroLock storage.</p></div><label className={`button button-small upload-button ${busy?'disabled':''}`}><UploadCloud size={17}/>{busy?'Uploadingâ€¦':'Upload file'}<input type="file" onChange={upload} disabled={busy} hidden/></label></div>
      <div className="file-table-head"><span>FILE NAME</span><span>SIZE</span><span>DATE ADDED</span><span>ACTIONS</span></div>
      {loading?<div className="empty-state"><div className="spinner"/><p>Loading your filesâ€¦</p></div>:files.length===0?<div className="empty-state"><div className="empty-icon"><FileLock2 size={28}/></div><h3>Your secure space is ready</h3><p>Upload your first file to see it here. Start with a non-sensitive test document.</p><label className="button button-ghost button-small"><UploadCloud size={16}/> Choose a file<input type="file" onChange={upload} hidden/></label></div>:files.map(file=><div className="file-row" key={file.id}><div className="file-name"><span className="file-icon"><FileText size={18}/></span><strong>{file.original_name}</strong></div><span>{formatSize(file.size_bytes||0)}</span><span>{new Date(file.created_at).toLocaleDateString()}</span><div className="file-actions"><button title="Open file" onClick={()=>openFile(file)}><Download size={17}/></button><button title="Delete file" onClick={()=>removeFile(file)}><Trash2 size={17}/></button></div></div>)}
    </div>
    <div className="dashboard-bottom"><div className="panel security-panel"><div className="side-icon"><ShieldCheck/></div><div><h3>Security setup</h3><p>Use account authentication, complete typing enrollment, and keep your email alerts configured.</p><div className="panel-links"><Link to="/typing-analysis">Complete typing analysis <ArrowRight size={15}/></Link></div></div></div><div className="panel security-panel"><div className="side-icon side-icon-blue"><Mail/></div><div><h3>Email alert test</h3><p>Send a test alert to the email address on your signed-in account, if Gmail SMTP is configured.</p><button className="text-button" onClick={alertMe}>Send test alert <ArrowRight size={15}/></button></div></div></div>
    <p className="fine-print">Prototype notice: this dashboard uses account authorization and private storage, but the behavioral matcher is not production validated. Do not upload sensitive or irreplaceable files during testing.</p>
  </section>
}

function RequireSession({ session, loading, children }) {
  if (loading) return <div className="loading-screen"><div className="spinner"/><p>Loading NeuroLock…</p></div>
  return session ? children : <Navigate to="/login" replace/>
}

function Protected({ session, loading, biometric, children }) {
  if (loading) return <div className="loading-screen"><div className="spinner"/><p>Loading NeuroLock…</p></div>
  if (!session) return <Navigate to="/login" replace/>
  if (biometric.loading) return <div className="loading-screen"><div className="spinner"/><p>Checking your second factor…</p></div>
  if (!biometric.verified) return <Navigate to="/verify" replace/>
  return children
}
export default function App() {
  const {session,loading,recovery}=useSession()
  const navigate = useNavigate()
  useEffect(() => {
    // If Supabase redirected a confirmation link to the Site URL (for example
    // "/"), move it to the dedicated route that completes the flow.
    if (isEmailConfirmationRedirect && window.location.pathname !== '/confirm') {
      navigate('/confirm', { replace: true })
    }
  }, [navigate])
  return <Layout session={session}><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/register" element={session?<Navigate to="/dashboard"/>:<AuthPage mode="register"/>}/>
    <Route path="/login" element={session?<Navigate to="/dashboard"/>:<AuthPage mode="login"/>}/>
    <Route path="/confirm" element={<ConfirmEmail/>}/>
    <Route path="/forgot-password" element={<ForgotPassword/>}/>
    <Route path="/reset-password" element={<ResetPassword session={session} loading={loading} recovery={recovery}/>}/>
    <Route path="/typing-analysis" element={<RequireSession session={session} loading={loading}><TypingAnalysis/></RequireSession>}/>
    <Route path="/verify" element={<Navigate to="/dashboard" replace/>}/>
    <Route path="/dashboard" element={<RequireSession session={session} loading={loading}><Dashboard/></RequireSession>}/>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes></Layout>
}
