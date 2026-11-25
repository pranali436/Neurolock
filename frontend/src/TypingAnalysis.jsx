import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CheckCircle2, Fingerprint, LockKeyhole, RotateCcw, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from './api'
import { TYPING_SAMPLES } from './typingSamples'
import './typing-analysis.css'

const EMPTY_ATTEMPTS = () => Array(TYPING_SAMPLES.length).fill(null)

function accuracyFor(value, target) {
  if (!value) return 0
  let matches = 0
  for (let index = 0; index < Math.min(value.length, target.length); index += 1) {
    if (value[index] === target[index]) matches += 1
  }
  return matches / Math.max(value.length, target.length)
}

function Metric({ label, value }) {
  return <div className="typing-analysis-metric"><span>{label}</span><strong>{value}</strong></div>
}

function ScoreBar({ label, value }) {
  return <div className="typing-analysis-bar">
    <div><span>{label}</span><strong>{value == null ? '—' : `${Math.round(value)}%`}</strong></div>
    <div className="typing-analysis-track"><span style={{ width: `${Math.min(100, Math.max(0, value || 0))}%` }}/></div>
  </div>
}

export default function TypingAnalysis() {
  const [attempts, setAttempts] = useState(EMPTY_ATTEMPTS)
  const [sampleIndex, setSampleIndex] = useState(0)
  const [value, setValue] = useState('')
  const [active, setActive] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [result, setResult] = useState(null)
  const [baselineAvailable, setBaselineAvailable] = useState(null)
  const [checkingBaseline, setCheckingBaseline] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)
  const activeRef = useRef(false)
  const startTimeRef = useRef(0)
  const firstKeyTimeRef = useRef(null)
  const downCodesRef = useRef(new Set())
  const eventsRef = useRef([])
  const phrase = TYPING_SAMPLES[sampleIndex]
  const capturedCount = attempts.filter(Boolean).length
  const elapsedSeconds = elapsedMs / 1000
  const liveWpm = elapsedMs > 0
    ? Math.round((value.length / 5) / (elapsedMs / 60_000))
    : 0
  const liveAccuracy = Math.round(accuracyFor(value, phrase) * 100)

  useEffect(() => {
    let mounted = true
    api('/api/biometric/status')
      .then(status => { if (mounted) setBaselineAvailable(Boolean(status.enrolled)) })
      .catch(requestError => {
        if (mounted) {
          setBaselineAvailable(null)
          setError(requestError.message || 'Could not check your typing enrollment status.')
        }
      })
      .finally(() => { if (mounted) setCheckingBaseline(false) })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!active) return undefined
    const timer = window.setInterval(() => {
      if (firstKeyTimeRef.current !== null) {
        setElapsedMs(performance.now() - firstKeyTimeRef.current)
      }
    }, 200)
    inputRef.current?.focus()
    return () => window.clearInterval(timer)
  }, [active])

  async function submitAttempts(nextAttempts) {
    setBusy(true)
    setError('')
    try {
      const response = await api('/api/typing-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ samples: nextAttempts }),
      })
      setResult(response)
    } catch (requestError) {
      setError(requestError.message || 'Typing analysis could not be completed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function begin(index = attempts.findIndex(sample => !sample)) {
    const nextIndex = index < 0 ? 0 : index
    const nextAttempts = [...attempts]
    nextAttempts[nextIndex] = null
    setAttempts(nextAttempts)
    setSampleIndex(nextIndex)
    setValue('')
    setElapsedMs(0)
    setError('')
    setResult(null)
    eventsRef.current = []
    downCodesRef.current = new Set()
    firstKeyTimeRef.current = null
    startTimeRef.current = performance.now()
    activeRef.current = true
    setActive(true)
  }

  function onKeyDown(event) {
    if (!activeRef.current) return
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()
      if (event.key.toLowerCase() === 'v') {
        setError('Pasting is disabled. Type the phrase to capture real key timing.')
      }
      return
    }
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Delete'].includes(event.key)) {
      event.preventDefault()
      return
    }
    if (event.key !== 'Backspace' && event.key.length !== 1) return
    setError('')

    const now = performance.now()
    const code = event.code || event.key
    const repeat = event.repeat
    if (repeat && !downCodesRef.current.has(code)) return
    eventsRef.current.push({
      kind: 'keydown',
      key: event.key,
      code,
      time_ms: now - startTimeRef.current,
      repeat,
    })
    if (!repeat) downCodesRef.current.add(code)
    if (event.key !== 'Backspace' && firstKeyTimeRef.current === null) {
      firstKeyTimeRef.current = now
      setElapsedMs(0)
    }
  }

  function onKeyUp(event) {
    if (!activeRef.current) return
    const code = event.code || event.key
    if (!downCodesRef.current.has(code)) return
    eventsRef.current.push({
      kind: 'keyup',
      key: event.key,
      code,
      time_ms: performance.now() - startTimeRef.current,
      repeat: false,
    })
    downCodesRef.current.delete(code)
  }

  function blockPaste(event) {
    event.preventDefault()
    setError('Pasting is disabled. Type the phrase to capture real key timing.')
  }

  function onBeforeInput(event) {
    const inputType = event.nativeEvent.inputType || ''
    if (/paste|drop|replacement/i.test(inputType)) blockPaste(event)
  }

  async function finishSample(event) {
    event.preventDefault()
    if (!activeRef.current) return
    activeRef.current = false
    setActive(false)
    setElapsedMs(
      firstKeyTimeRef.current === null
        ? 0
        : performance.now() - firstKeyTimeRef.current,
    )
    const nextAttempts = [...attempts]
    nextAttempts[sampleIndex] = {
      typed_text: value,
      events: eventsRef.current,
    }
    setError('')
    setAttempts(nextAttempts)
    setValue('')
    const nextIndex = nextAttempts.findIndex(sample => !sample)
    if (nextIndex >= 0) setSampleIndex(nextIndex)
    else await submitAttempts(nextAttempts)
  }

  function retakeTest() {
    setAttempts(EMPTY_ATTEMPTS())
    setSampleIndex(0)
    setValue('')
    setResult(null)
    setError('')
    setElapsedMs(0)
    activeRef.current = false
    setActive(false)
  }

  const completedSamples = result?.samples || []

  return <section className="page wrap typing-analysis-page">
    <div className="page-heading">
      <div className="eyebrow">BEHAVIORAL BIOMETRICS</div>
      <h1>Keystroke score &amp; typing speed</h1>
      <p>Type the three existing NeuroLock prompts. Speed, accuracy and typing rhythm are measured separately; speed alone never determines your score.</p>
    </div>

    <div className="typing-analysis-layout">
      <div className="panel typing-analysis-main">
        <div className="typing-analysis-heading">
          <div className="side-icon"><Fingerprint size={25}/></div>
          <div><h2>Three-sample typing test</h2><p>Use your usual pace. Do not enter a password or other private text here.</p></div>
        </div>
        <div className="sample-progress">
          <div className="progress-label"><span>Samples captured</span><strong>{capturedCount} / {TYPING_SAMPLES.length}</strong></div>
          <div className="progress-track"><div style={{ width: `${capturedCount / TYPING_SAMPLES.length * 100}%` }}/></div>
          <div className="sample-dots" aria-label={`${capturedCount} of ${TYPING_SAMPLES.length} samples captured`}>
            {TYPING_SAMPLES.map((_, index) => <span key={index} className={attempts[index] ? 'sample-dot completed' : 'sample-dot'}>
              {attempts[index] ? <CheckCircle2 size={16}/> : index + 1}
            </span>)}
          </div>
        </div>

        <div className="typing-analysis-prompt">
          <span>SAMPLE {sampleIndex + 1} OF {TYPING_SAMPLES.length}</span>
          <strong>{phrase}</strong>
          <button type="button" className="button button-small" onClick={() => begin(sampleIndex)} disabled={active || busy}>
            {active ? 'Typing…' : attempts[sampleIndex] ? 'Retake this sample' : 'Start sample'}
          </button>
        </div>

        <form onSubmit={finishSample}>
          <label className="typing-label">
            Type the phrase
            <input
              ref={inputRef}
              value={value}
              onChange={event => {
                if (activeRef.current) setValue(event.target.value)
              }}
              onKeyDown={onKeyDown}
              onKeyUp={onKeyUp}
              onBeforeInput={onBeforeInput}
              onPaste={blockPaste}
              onCut={blockPaste}
              onDrop={blockPaste}
              onClick={event => event.currentTarget.setSelectionRange(value.length, value.length)}
              disabled={!active || busy}
              maxLength={120}
              placeholder={active ? 'Type the prompt above…' : 'Select “Start sample” first'}
              autoComplete="off"
              spellCheck="false"
              autoCapitalize="off"
            />
          </label>
          <div className="typing-analysis-live">
            <Metric label="Elapsed time" value={`${elapsedSeconds.toFixed(1)} s`}/>
            <Metric label="Live WPM" value={liveWpm}/>
            <Metric label="Live accuracy" value={`${liveAccuracy}%`}/>
          </div>
          <div className="form-row">
            <span className="muted">{active ? 'Real key events are being timed.' : 'Pasting and drag-and-drop are disabled.'}</span>
            <button type="submit" className="button button-small" disabled={!active || busy}>
              {busy ? 'Analyzing…' : 'Save sample'} <ArrowRight size={15}/>
            </button>
          </div>
        </form>

        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {busy && <div className="alert alert-info" role="status">Calculating sample metrics and score…</div>}
        {capturedCount === TYPING_SAMPLES.length && !result && !busy &&
          <button className="button button-full" type="button" onClick={() => submitAttempts(attempts)}>
            {error ? 'Retry analysis' : 'Analyze all three samples'} <ArrowRight size={16}/>
          </button>}
        {result && <button className="button button-ghost button-full" type="button" onClick={retakeTest}>
          <RotateCcw size={15}/> Start a new three-sample test
        </button>}
      </div>

      <aside className="panel typing-analysis-side">
        {result?.complete
          ? <div className="typing-analysis-score">
              <span>OVERALL KEYSTROKE SCORE</span>
              <strong>{Math.round(result.keystroke_score)}<small> / 100</small></strong>
              <p>{result.consistency_summary}</p>
            </div>
          : <div className="typing-analysis-score typing-analysis-score-empty">
              <span>OVERALL KEYSTROKE SCORE</span>
              <strong>—<small> / 100</small></strong>
              <p>{result ? 'Complete all three prompts with valid timing to calculate the overall score.' : 'Complete all three prompts to see your score and summary.'}</p>
            </div>}
        <div className="typing-analysis-summary">
          <Metric label="Average typing speed" value={result?.average_wpm == null ? '—' : `${result.average_wpm} WPM`}/>
          <Metric label="Baseline status" value={result ? (result.baseline_available ? 'Enrolled' : 'Not enrolled') : checkingBaseline ? 'Checking…' : baselineAvailable ? 'Enrolled' : baselineAvailable === false ? 'Not enrolled' : 'Unavailable'}/>
        </div>
        {result?.complete && <div className="typing-analysis-breakdown">
          <h3>Score breakdown</h3>
          <ScoreBar label="Final-text accuracy · 40%" value={result.score_breakdown.accuracy_percent}/>
          <ScoreBar label="Within-sample rhythm · 30%" value={result.score_breakdown.within_sample_rhythm_percent}/>
          <ScoreBar label="Between-sample consistency · 30%" value={result.score_breakdown.between_sample_consistency_percent}/>
        </div>}
        {result?.complete && <div className="typing-analysis-performance">
          <div><span>Typing speed</span><strong>{result.average_wpm} WPM</strong><small>Separate from score</small></div>
          <div><span>Accuracy</span><strong>{result.score_breakdown.accuracy_percent}%</strong><small>Correct final text</small></div>
          <div><span>Rhythm</span><strong>{result.score_breakdown.within_sample_rhythm_percent}%</strong><small>Timing consistency</small></div>
        </div>}
        {result && <div className="typing-analysis-baseline">
          <h3><ShieldCheck size={17}/> Enrolled rhythm comparison</h3>
          {result.baseline_available
            ? <><strong>{result.baseline_similarity_percent == null ? '—' : `${result.baseline_similarity_percent}%`}</strong><p>{result.baseline_message}</p></>
            : <p>{result.baseline_message} This comparison is separate from typing speed and the keystroke score.</p>}
        </div>}
        <div className="privacy-note"><LockKeyhole size={17}/><p>Key event timings are sent only for this calculation and are not saved. Pasted input is blocked. The score is a descriptive prototype metric, not proof of identity.</p></div>
        <Link className="button button-ghost button-full" to="/enrollment">Manage typing enrollment <ArrowRight size={15}/></Link>
      </aside>
    </div>

    {result && <section className="typing-analysis-results" aria-live="polite">
      <div className="typing-analysis-results-heading">
        <div><div className="eyebrow">SAMPLE RESULTS</div><h2>{result.complete ? 'Your typing analysis' : 'Incomplete test'}</h2></div>
        {result.complete && <span className="typing-analysis-complete"><CheckCircle2 size={16}/> Analysis complete</span>}
      </div>
      <div className="typing-analysis-cards">
        {completedSamples.map((sample, index) => <article className="panel typing-analysis-card" key={sample.sample_number}>
          <div className="typing-analysis-card-head">
            <h3>Sample {index + 1}</h3>
            <span className={sample.complete ? 'typing-analysis-status complete' : 'typing-analysis-status incomplete'}>
              {sample.complete ? 'Complete' : 'Incomplete'}
            </span>
          </div>
          <p className="typing-analysis-text">{TYPING_SAMPLES[index]}</p>
          {sample.completion_message && <p className="typing-analysis-warning">{sample.completion_message}</p>}
          <div className="typing-analysis-metrics-grid">
            <Metric label="Sample score" value={sample.keystroke_score == null ? '—' : `${sample.keystroke_score} / 100`}/>
            <Metric label="Typing speed" value={sample.wpm == null ? '—' : `${sample.wpm} WPM`}/>
            <Metric label="Total time" value={sample.total_time_seconds == null ? '—' : `${sample.total_time_seconds} s`}/>
            <Metric label="Correct characters" value={`${sample.correct_characters} / ${Math.max(TYPING_SAMPLES[index].length, sample.typed_characters)}`}/>
            <Metric label="Accuracy" value={`${sample.accuracy_percent}%`}/>
            <Metric label="Mean key dwell" value={sample.average_dwell_ms == null ? '—' : `${sample.average_dwell_ms} ms`}/>
            <Metric label="Mean inter-key latency" value={sample.average_inter_key_latency_ms == null ? '—' : `${sample.average_inter_key_latency_ms} ms`}/>
            <Metric label="Rhythm consistency" value={sample.rhythm_consistency_percent == null ? '—' : `${sample.rhythm_consistency_percent}%`}/>
          </div>
          {!sample.complete && <button className="text-button" type="button" onClick={() => begin(index)}>Retake Sample {index + 1} <ArrowRight size={14}/></button>}
        </article>)}
      </div>
      <p className="typing-analysis-explanation">{result.score_note}</p>
    </section>}
  </section>
}
