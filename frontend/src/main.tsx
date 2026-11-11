import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/instrument-sans';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import './style.css';
import {
  batchNames, count, dayLabel, grainLabels, grains, headline, lastDay,
  money, monthLabel, phaseLabels, signed,
} from './contract';
import type { Grain, Row, State, Summary } from './contract';

type Command = (path: string, body?: object, label?: string) => Promise<void>;

async function request(path: string, body?: object): Promise<State> {
  const response = await fetch('/api/' + path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined);
  const payload = await response.json();
  if (!response.ok) {
    const message = typeof payload.detail === 'string' ? payload.detail : 'The request could not be completed.';
    if (response.status === 409) throw new StaleAction(message);
    throw new Error(message);
  }
  return payload;
}

class StaleAction extends Error {}

function App() {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [grain, setGrain] = useState<Grain>('zone');
  const [day, setDay] = useState(headline);

  useEffect(() => {
    request('state').then(setState).catch(() => setError('Could not connect to the rehearsal server.'));
  }, []);
  useEffect(() => {
    if (state) document.title = state.brand.name + ' · ' + state.brand.subtitle;
  }, [state?.brand.name, state?.brand.subtitle]);

  const action: Command = async (path, body = {}, label = 'Updating rehearsal…') => {
    if (!state || busy) return;
    setBusy(label);
    setError('');
    try {
      setState(await request(path, { version: state.version, ...body }));
      if (path === 'reset') {
        setGrain('zone');
        setDay(headline);
      }
      if (path === 'selection' && 'scenario' in body) {
        setGrain(body.scenario === 'wrong_day' ? 'day' : body.scenario === 'stale' ? 'month' : 'zone');
        setDay(headline);
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The request failed.');
      if (failure instanceof StaleAction) {
        try { setState(await request('state')); } catch { /* Keep the visible request error. */ }
      }
    } finally {
      setBusy('');
    }
  };

  if (!state) return <main className="loading" role={error ? 'alert' : 'status'}>{error || 'Loading rehearsal…'}</main>;
  const comparison = state.comparison;
  const old = comparison?.source.focus[day] ?? (state.report?.backend === 'DuckDB source' ? state.report.focus[day] : null);
  const candidate = comparison?.candidate.focus[day];
  const matching = old && candidate && old.trips === candidate.trips && old.fee_cents === candidate.fee_cents;
  const cloudRead = comparison?.candidate.live || state.report?.live;
  const mode = cloudRead ? 'Live warehouse' : state.target === 'local' ? 'Local rehearsal' : 'Live check pending';

  return <>
    <header className="masthead">
      <div className="frame mast-inner">
        <div className="brand">
          <span className="mark" aria-hidden="true">{state.brand.mark}</span>
          <div><strong>{state.brand.name}</strong><span>{state.brand.subtitle}</span></div>
        </div>
        <div className="mode"><i aria-hidden="true" />{mode}<span className="mode-data">{state.mode === 'full' ? 'TLC public files' : 'Sample fixture'}</span></div>
      </div>
    </header>
    <main className="frame main">
      <div className="intro">
        <div><p className="eyebrow">NYC YELLOW TAXI / FINANCE REPORT</p><h1>Migration review</h1></div>
        <dl className="context">
          <div><dt>Selected target</dt><dd>{state.targets[state.target]}</dd></div>
          <div><dt>Serving backend</dt><dd>{state.report?.backend ?? 'Unavailable'}</dd></div>
          <div><dt>Batch through</dt><dd>{lastDay(state.batch.as_of)}</dd></div>
        </dl>
      </div>

      <div className="top-grid">
        <section className="surface snapshot" aria-labelledby="snapshot-title">
          <div className="surface-head">
            <div><h2 id="snapshot-title">Daily report</h2><p>{dayLabel(day)} pickups</p></div>
            {matching && <span className="tag match"><b aria-hidden="true">✓</b> Totals match</span>}
          </div>
          <div className="totals">
            <Metrics label="Old system" summary={old} />
            <Metrics label="Candidate" summary={candidate} />
          </div>
        </section>

        <section className={'surface decision ' + state.phase} aria-labelledby="decision-title" aria-live="polite">
          <div className="eyebrow decision-label"><i aria-hidden="true" />Cutover decision</div>
          <h2 id="decision-title">{phaseLabels[state.phase]}</h2>
          <p>{state.detail}</p>
          {state.recovery && <div className="recovery">
            <span>{state.recovery.kind} failure{state.recovery.milliseconds != null ? ' · ' + state.recovery.milliseconds.toFixed(2) + ' ms recovery' : ''}</span>
            <span>{state.recovery.reason}</span>
          </div>}
          {!state.recovery && comparison && <div className="check-list">
            {grains.map(key => <span key={key} data-failed={comparison.checks[key].failed > 0}>
              {comparison.checks[key].failed > 0 ? '×' : '✓'} {grainLabels[key]}
            </span>)}
          </div>}
        </section>
      </div>

      <Controls state={state} busy={busy} action={action} />
      {error && <p className="error" role="alert">{error}</p>}

      <div className="detail-grid">
        <Evidence state={state} grain={grain} setGrain={setGrain} day={day} setDay={setDay} />
        <section className="surface activity" aria-labelledby="activity-title">
          <div className="surface-head"><div><h2 id="activity-title">Activity</h2><p>Most recent actions</p></div></div>
          <ol className="events">
            {state.events.slice(-5).reverse().map((event, i) => <li key={event.time + event.label + i}>
              <span className="event-dot" aria-hidden="true" />
              <div>
                <strong>{event.label}</strong>
                {event.backend && <p className="event-meta">{event.backend} · {event.batch === 'current' ? 'Dec + Jan' : 'December only'}</p>}
                {event.note && <p>{event.note}</p>}
              </div>
              <time dateTime={event.time}>{new Date(event.time).toLocaleTimeString('en-US', { hour12: false })}</time>
            </li>)}
          </ol>
          {state.report && <div className="served">
            <span className="eyebrow">Active report · {dayLabel(day)}</span>
            <strong>{state.report.backend}</strong>
            <span className="mono">{count(state.report.focus[day]?.trips)} trips · {money(state.report.focus[day]?.fee_cents)}</span>
          </div>}
        </section>
      </div>
      <details className="provenance">
        <summary>Batch and report provenance</summary>
        <dl>
          <div><dt>Expected batch</dt><dd>{batchNames[state.batch.name]}</dd></div>
          {comparison && <div><dt>Candidate batch</dt><dd>{batchNames[comparison.candidate.batch.name]}</dd></div>}
          {state.batch.inputs.map(input => <div key={input.file}><dt>{input.file}</dt><dd className="mono">{input.sha256}</dd></div>)}
          <div><dt>Zone lookup SHA-256</dt><dd className="mono">{state.batch.zone_lookup_sha256}</dd></div>
          {comparison && <div><dt>Candidate report revision</dt><dd className="mono">{comparison.candidate.revision}</dd></div>}
          {state.report && <div><dt>Serving report revision</dt><dd className="mono">{state.report.revision}</dd></div>}
        </dl>
      </details>
      <footer>TLC yellow taxi records · Simulated reporting faults and cutover decisions</footer>
    </main>
  </>;
}

function Metrics({ label, summary }: { label: string; summary?: Summary | null }) {
  return <div className="metrics">
    <h3><span aria-hidden="true" />{label}</h3>
    <dl><div><dt>Trips</dt><dd>{count(summary?.trips)}</dd></div>
    <div><dt>Recorded CBD fees</dt><dd>{money(summary?.fee_cents)}</dd></div></dl>
  </div>;
}

function Controls({ state, busy, action }: { state: State; busy: string; action: Command }) {
  const [failure, setFailure] = useState('candidate');
  const active = ['switched', 'fallback', 'unavailable'].includes(state.phase);
  const select = (change: object) => void action('selection', {
    target: state.target, scenario: state.scenario, batch: state.batch.name, ...change,
  });
  return <section className="surface controls" aria-label="Rehearsal controls" aria-busy={!!busy}>
    <div className="selectors">
      <label>Target<select value={state.target} disabled={!!busy || active} onChange={event => select({ target: event.target.value })}>
        {Object.entries(state.targets).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Scenario<select value={state.scenario} disabled={!!busy || active} onChange={event => select({ scenario: event.target.value })}>
        {Object.entries(state.scenarios).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Batch<select value={state.batch.name} disabled={!!busy || active} onChange={event => select({ batch: event.target.value })}>
        {Object.entries(batchNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
    </div>
    <div className="buttons">
      <button disabled={!!busy || active} onClick={() => void action('check', {}, 'Running warehouse checks…')}>Run checks</button>
      <button className="primary" disabled={!!busy || !state.approval}
        onClick={() => void action('switch', { approval: state.approval }, 'Reading the approved candidate…')}>Switch to cloud <span aria-hidden="true">↗</span></button>
      <button disabled={!!busy || state.phase !== 'switched'}
        onClick={() => void action('failure', { injection: failure }, 'Verifying fallback…')}>Simulate failure</button>
      <button className="quiet" disabled={!!busy} onClick={() => { setFailure('candidate'); void action('reset'); }}>Reset</button>
    </div>
    <div className="controls-foot">
      <span role="status">{busy || (state.phase === 'switched' ? 'The approved candidate is serving. You can test recovery.' :
        active ? 'Reset to start a new rehearsal.' : state.approval ? 'Approve the cutover when ready.' : 'Switching requires a fresh passing check.')}</span>
      {state.phase === 'switched' && <div className="failure-controls">
        <button className="quiet refresh" disabled={!!busy} onClick={() => void action('report', {}, 'Reading the active report…')}>Refresh active report</button>
        <label>Failure test<select value={failure} disabled={!!busy} onChange={event => setFailure(event.target.value)}>
          <option value="candidate">Candidate only</option><option value="stale">Stale source</option>
          <option value="unavailable">Unavailable source</option>
        </select></label>
      </div>}
    </div>
  </section>;
}

function Evidence({ state, grain, setGrain, day, setDay }: {
  state: State; grain: Grain; setGrain: (grain: Grain) => void; day: string; setDay: (day: string) => void;
}) {
  const allRows = state.comparison?.rows ?? [];
  const rows = allRows.filter(row => row.grain === grain && (grain !== 'zone' || row.day === day));
  rows.sort((a, b) => Number(!!b.issues.length) - Number(!!a.issues.length) ||
    (b.old?.trips ?? 0) - (a.old?.trips ?? 0));
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, grain === 'zone' ? 5 : rows.length);
  return <section className="surface evidence" aria-labelledby="evidence-title">
    <div className="surface-head">
      <div><h2 id="evidence-title">Reconciliation</h2><p>Recorded CBD fees and pickup counts</p></div>
      <div className="tabs" aria-label="Report grain">
        {grains.map(key => <button key={key} aria-pressed={key === grain}
          onClick={() => { setGrain(key); setExpanded(false); }}>{grainLabels[key]}</button>)}
      </div>
    </div>
    <div className="slice">
      <span>{grain === 'zone' ? 'Pickup day' : 'Candidate minus old system'}</span>
      {grain === 'zone' && <select aria-label="Pickup day" value={day} onChange={event => { setDay(event.target.value); setExpanded(false); }}>
        <option value="2025-01-06">Jan 6, 2025</option><option value="2025-01-07">Jan 7, 2025</option>
      </select>}
    </div>
    {shown.length ? <>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable reconciliation table">
        <table>
          <thead><tr><th scope="col">{grainLabels[grain]}</th><th scope="col">Old system</th><th scope="col">Candidate</th><th scope="col">Difference</th></tr></thead>
          <tbody>{shown.map(row => <EvidenceRow key={`${row.grain}-${row.month}-${row.day}-${row.zone}`} row={row} />)}</tbody>
        </table>
      </div>
      <div className="table-foot">
        <span>{count(state.comparison?.checks[grain].groups)} {grainLabels[grain].toLowerCase()} groups checked</span>
        {rows.length > 5 && grain === 'zone' && <button className="quiet" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show fewer' : `Show all ${rows.length} zones`}
        </button>}
      </div>
    </> : <p className="empty">{state.comparison ? 'No groups for this slice.' : 'Run checks to see the comparison.'}</p>}
  </section>;
}

function EvidenceRow({ row }: { row: Row }) {
  const label = row.grain === 'zone' ? row.zone_name : row.day ? dayLabel(row.day) : monthLabel(row.month);
  return <tr className={row.issues.length ? 'difference' : ''}>
    <th scope="row">{label}{row.zone != null && <span className="zone-id">{row.zone}</span>}
      {!!row.issues.length && <small className="issue">{row.issues.join(', ')}</small>}
    </th>
    {[row.old, row.candidate].map((summary, i) => <td key={i}>
      <span>{summary?.has_fee === 0 ? 'Unavailable' : money(summary?.fee_cents)}</span>
      <small>{count(summary?.trips)} trips</small>
    </td>)}
    <td><strong>{signed(row.fee_difference, money)}</strong>
      <small>{row.trip_difference == null ? '—' : signed(row.trip_difference, count) + ' trips'}</small>
    </td>
  </tr>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
