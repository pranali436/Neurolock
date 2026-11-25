import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { ShieldCheck, LockKeyhole, Fingerprint, FileLock2, ArrowRight, UploadCloud, FileText, LogOut, LayoutDashboard, CheckCircle2, AlertCircle, Trash2, Download, Mail, Menu, X } from 'lucide-react'
import { supabase } from './supabase'
import { api } from './api'

function useSession() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false) })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])
  return { session, loading }
}

function Layout({ children, session }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  async function logout() { await supabase.auth.signOut(); navigate('/') }
  return <div className="app-shell">
    <header className="topbar">
      <Link className="brand" to="/"><span className="brand-mark"><ShieldCheck size={22}/></span><span>Neuro<span className="brand-blue">Lock</span><small>BEHAVIORAL SECURITY</small></span></Link>
      <button className="mobile-toggle" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle menu">{mobileOpen ? <X/> : <Menu/>}</button>
      <nav className={mobileOpen ? 'nav nav-open' : 'nav'}>
        {session ? <><NavLink to="/dashboard" onClick={() => setMobileOpen(false)}>Dashboard</NavLink><NavLink to="/enrollment" onClick={() => setMobileOpen(false)}>Enrollment</NavLink><button className="nav-signout" onClick={logout}><LogOut size={16}/> Sign out</button></> :
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
  const navigate = useNavigate()
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      if (mode === 'register') {
        const { data, error } = await supabase.auth.signUp({ email, password, options:{ data:{ display_name:name } } })
        if (error) throw error
        if (!data.session) { setMessage('Check your inbox to confirm your email, then sign in.'); return }
        navigate('/enrollment')
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
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
      <label>Password<input type="password" autoComplete={mode==='register'?'new-password':'current-password'} minLength={8} value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" required/></label>
      {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}
      {message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
      <button className="button button-full" disabled={busy}>{busy?'Please waitâ€¦':mode==='register'?'Create account':'Sign in'} <ArrowRight size={17}/></button>
    </form><div className="auth-switch">{mode==='register'?'Already have an account?':'New to NeuroLock?'} <Link to={mode==='register'?'/login':'/register'}>{mode==='register'?'Sign in':'Create an account'}</Link></div>
    <p className="fine-print">Use a unique password. Behavioral matching here is a prototype and is not a substitute for strong authentication.</p>
  </div></section>
}

function Enrollment() {
  const phrase = 'My typing rhythm protects my files'
  const [value,setValue] = useState('')
  const [samples,setSamples] = useState([])
  const [active,setActive] = useState(false)
  const [start,setStart] = useState(0)
  const [down,setDown] = useState({})
  const [dwells,setDwells] = useState([])
  const [flights,setFlights] = useState([])
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [done,setDone] = useState(false)
  function begin() {
  console.log("START SAMPLE BUTTON CLICKED");
  setValue('');
  setDwells([]);
  setFlights([]);
  setDown({});
  window.__neurolockKeyDown = {};
  window.__neurolockLastKeyUp = 0;
  setStart(performance.now());
  setActive(true);
  setMessage('Type the exact phrase below. Timing is captured only while this field is active.');
 }
  function keyDown(e) {
    if (!active || e.repeat || e.key.length !== 1) return
    const now=performance.now()
    window.__neurolockKeyDown = window.__neurolockKeyDown || {}
    window.__neurolockKeyDown[e.key] = now
    if (window.__neurolockLastKeyUp) {
      setFlights(prev=>[...prev,Math.max(0,now-window.__neurolockLastKeyUp)])
    }
  }
  function keyUp(e) {
    if (!active || e.key.length !== 1) return
    const now=performance.now()
    const pressedAt = window.__neurolockKeyDown?.[e.key]
    if (pressedAt !== undefined) {
      setDwells(prev=>[...prev,Math.max(0,now-pressedAt)])
      delete window.__neurolockKeyDown[e.key]
    }
    window.__neurolockLastKeyUp=now
  }
  function finishSample(e) {
    e.preventDefault()
    if(value !== phrase) { setError('Please type the exact phrase, including spaces and capitalization.'); return }
    if(dwells.length < 10) { setError('Not enough timing data was captured. Select Start sample and type the phrase again.'); return }
    const mean = arr => arr.reduce((a,b)=>a+b,0)/(arr.length||1)
    const variance = arr => {const m=mean(arr);return mean(arr.map(x=>(x-m)**2))}
    const features={mean_dwell:mean(dwells),mean_flight:mean(flights),std_flight:Math.sqrt(variance(flights)),count:dwells.length}
    setSamples(prev=>[...prev,{features}].slice(0,5)); setActive(false); setValue(''); setError('')
    setMessage(`Sample captured (${Math.min(samples.length+1,5)} of 5).`)
  }
  async function save() {
    setBusy(true); setError(''); setMessage('')
    try { await api('/api/enrollment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({samples})}); setDone(true); setMessage('Enrollment saved successfully.'); }
    catch(e) {setError(e.message)}
    finally {setBusy(false)}
  }
  return <section className="page wrap"><div className="page-heading"><div className="eyebrow">BEHAVIORAL BIOMETRICS</div><h1>Enroll your typing pattern</h1><p>Type the same phrase five times so NeuroLock can create an initial timing baseline.</p></div>
    <div className="enroll-grid"><div className="panel enroll-main"><div className="step-line"><span className="step-number">1</span><div><h2>Capture your typing rhythm</h2><p>Use your normal pace. Avoid rushing or deliberately changing how you type.</p></div></div>
      <div className="phrase-box"><span>YOUR PHRASE</span><strong>{phrase}</strong><button type="button" className="text-button" onClick={begin}>{active?'Restart sample':'Start sample'}</button></div>
      <form onSubmit={finishSample}><label className="typing-label">Type the phrase here<input value={value} onChange={e=>setValue(e.target.value)} onKeyDown={keyDown} onKeyUp={keyUp} disabled={!active || done} placeholder={active?'Start typing the phraseâ€¦':'Select â€œStart sampleâ€ first'} autoComplete="off" spellCheck="false"/></label><div className="form-row"><span className="muted">{active?'Timing capture active':done?'Enrollment complete':'Timing capture paused'}</span><button className="button button-small" disabled={!active || done}>Save sample</button></div></form>
      {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}{message && <div className="alert alert-info">{message}</div>}
      <div className="sample-progress"><div className="progress-label"><span>Samples collected</span><strong>{samples.length} / 5</strong></div><div className="progress-track"><div style={{width:`${samples.length*20}%`}}/></div><div className="sample-dots">{[1,2,3,4,5].map(n=><span key={n} className={samples.length>=n?'sample-dot completed':'sample-dot'}>{samples.length>=n?<CheckCircle2 size={16}/>:n}</span>)}</div></div>
      <button className="button button-full" onClick={save} disabled={samples.length<5||busy||done}>{busy?'Saving enrollmentâ€¦':done?'Enrollment saved':'Save typing baseline'} <ArrowRight size={17}/></button>
    </div><aside className="panel enroll-side"><div className="side-icon"><Fingerprint size={25}/></div><h3>What is being measured?</h3><ul className="check-list"><li><CheckCircle2/> Key press duration</li><li><CheckCircle2/> Time between keystrokes</li><li><CheckCircle2/> Variation in typing rhythm</li><li><CheckCircle2/> Sample consistency</li></ul><div className="privacy-note"><LockKeyhole size={17}/><p>Use the provided phrase only. Never type your real password into this enrollment field. This starter stores derived timing features, not the phrase.</p></div><Link className="button button-ghost button-full" to="/dashboard">Go to dashboard <ArrowRight size={16}/></Link></aside></div>
  </section>
}

function Dashboard() {
  const [files,setFiles] = useState([])
  const [loading,setLoading] = useState(true)
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  const [enrolled,setEnrolled] = useState(null)
  async function refresh() {
    setLoading(true); setError('')
    try {const data=await api('/api/files');setFiles(data.files||[]); try {await api('/api/biometric/status');setEnrolled(true)} catch {setEnrolled(null)}}
    catch(e){setError(e.message)}
    finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[])
  async function upload(e) {
    const file=e.target.files?.[0]; if(!file)return
    setBusy(true);setMessage('');setError('')
    try {const form=new FormData();form.append('file',file);await api('/api/files',{method:'POST',body:form});setMessage(`${file.name} uploaded securely.`);await refresh()}
    catch(err){setError(err.message)}
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
  return <section className="page wrap"><div className="dashboard-welcome"><div><div className="eyebrow">YOUR PRIVATE WORKSPACE</div><h1>Dashboard</h1><p>Manage your files and review your security setup.</p></div><Link className="button button-small" to="/enrollment"><Fingerprint size={17}/> {enrolled?'Review enrollment':'Set up typing'}</Link></div>
    <div className="stat-grid"><div className="stat-card"><span className="stat-icon blue"><FileText/></span><div><span>Stored files</span><strong>{files.length}</strong></div></div><div className="stat-card"><span className="stat-icon green"><ShieldCheck/></span><div><span>Account status</span><strong>Protected</strong></div></div><div className="stat-card"><span className="stat-icon purple"><Fingerprint/></span><div><span>Typing baseline</span><strong>{enrolled===true?'Enrolled':'Check setup'}</strong></div></div></div>
    {error && <div className="alert alert-error"><AlertCircle size={17}/>{error}</div>}{message && <div className="alert alert-success"><CheckCircle2 size={17}/>{message}</div>}
    <div className="panel files-panel"><div className="panel-header"><div><h2>Your files</h2><p>Files in your private NeuroLock storage.</p></div><label className={`button button-small upload-button ${busy?'disabled':''}`}><UploadCloud size={17}/>{busy?'Uploadingâ€¦':'Upload file'}<input type="file" onChange={upload} disabled={busy} hidden/></label></div>
      <div className="file-table-head"><span>FILE NAME</span><span>SIZE</span><span>DATE ADDED</span><span>ACTIONS</span></div>
      {loading?<div className="empty-state"><div className="spinner"/><p>Loading your filesâ€¦</p></div>:files.length===0?<div className="empty-state"><div className="empty-icon"><FileLock2 size={28}/></div><h3>Your secure space is ready</h3><p>Upload your first file to see it here. Start with a non-sensitive test document.</p><label className="button button-ghost button-small"><UploadCloud size={16}/> Choose a file<input type="file" onChange={upload} hidden/></label></div>:files.map(file=><div className="file-row" key={file.id}><div className="file-name"><span className="file-icon"><FileText size={18}/></span><strong>{file.original_name}</strong></div><span>{formatSize(file.size_bytes||0)}</span><span>{new Date(file.created_at).toLocaleDateString()}</span><div className="file-actions"><button title="Open file" onClick={()=>openFile(file)}><Download size={17}/></button><button title="Delete file" onClick={()=>removeFile(file)}><Trash2 size={17}/></button></div></div>)}
    </div>
    <div className="dashboard-bottom"><div className="panel security-panel"><div className="side-icon"><ShieldCheck/></div><div><h3>Security setup</h3><p>Use account authentication, complete typing enrollment, and keep your email alerts configured.</p><Link to="/enrollment">Manage typing enrollment <ArrowRight size={15}/></Link></div></div><div className="panel security-panel"><div className="side-icon side-icon-blue"><Mail/></div><div><h3>Email alert test</h3><p>Send a test alert to the email address on your signed-in account, if Gmail SMTP is configured.</p><button className="text-button" onClick={alertMe}>Send test alert <ArrowRight size={15}/></button></div></div></div>
    <p className="fine-print">Prototype notice: this dashboard uses account authorization and private storage, but the behavioral matcher is not production validated. Do not upload sensitive or irreplaceable files during testing.</p>
  </section>
}

function Protected({ session, loading, children }) {
  if (loading) return <div className="loading-screen"><div className="spinner"/><p>Loading NeuroLockâ€¦</p></div>
  return session ? children : <Navigate to="/login" replace/>
}
export default function App() {
  const {session,loading}=useSession()
  return <Layout session={session}><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/register" element={session?<Navigate to="/dashboard"/>:<AuthPage mode="register"/>}/>
    <Route path="/login" element={session?<Navigate to="/dashboard"/>:<AuthPage mode="login"/>}/>
    <Route path="/enrollment" element={<Protected session={session} loading={loading}><Enrollment/></Protected>}/>
    <Route path="/dashboard" element={<Protected session={session} loading={loading}><Dashboard/></Protected>}/>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes></Layout>
}

