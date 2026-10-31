import React, { useState, useEffect } from 'react';
import type { BenchModels } from '../types/api';
import { api } from '../api';

interface BenchFormProps {
  onBenchmarkStarted: (id: string) => void;
}

export const BenchForm: React.FC<BenchFormProps> = ({ onBenchmarkStarted }) => {
  const [info, setInfo] = useState<BenchModels | null>(null);
  const [selectedSim, setSelectedSim] = useState<string[]>([]);
  const [realInput, setRealInput] = useState<string>('');
  const [focus, setFocus] = useState<string>('');
  const [nTests, setNTests] = useState<number>(10);
  const [repeats, setRepeats] = useState<number>(2);
  const [status, setStatus] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  useEffect(() => {
    document.title = 'Model benchmark · qe';
    api<BenchModels>('/api/benchmarks/models')
      .then((data) => {
        setInfo(data);
        setSelectedSim(data.simulated.map((m) => m.id));
      })
      .catch((e: any) => setStatus(`Could not load models: ${e.message}`));
  }, []);

  const handleSimToggle = (id: string) => {
    setSelectedSim((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleAddSuggestedReal = (modelName: string) => {
    if (!realInput) {
      setRealInput(modelName);
    } else if (!realInput.includes(modelName)) {
      setRealInput(`${realInput}, ${modelName}`);
    }
  };

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const realModels = realInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const models = [...selectedSim, ...realModels];

    if (!models.length) {
      setStatus('Please select at least one simulated or real model.');
      return;
    }

    setIsSubmitting(true);
    setStatus('Initializing comparative benchmark suite...');

    try {
      const res = await api<{ id: string }>('/api/benchmarks', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          models,
          focus,
          n_tests: Number(nTests),
          repeats: Number(repeats),
        }),
      });
      onBenchmarkStarted(res.id);
    } catch (e: any) {
      setStatus(`Could not start benchmark: ${e.message}`);
      setIsSubmitting(false);
    }
  };

  if (!info) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', color: '#64748b' }}>
        <span className="material-symbols-outlined" style={{ fontSize: '32px', animation: 'spin 2s linear infinite', color: '#4f46e5' }}>
          progress_activity
        </span>
        <p style={{ marginTop: '8px', fontSize: '14px' }}>Loading benchmark candidate models…</p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#4f46e5', fontWeight: 600, textTransform: 'uppercase' }}>
            Comparative Evaluation Studio
          </span>
          <span className="tag t-sim" style={{ fontSize: '10px' }}>
            Offline Replay Ready
          </span>
        </div>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-geist)', fontSize: '24px', fontWeight: 700, color: '#0f172a' }}>
          Model Benchmark Matrix
        </h1>
        <p style={{ margin: '6px 0 0', fontSize: '14px', color: '#64748b', lineHeight: 1.5 }}>
          Evaluate multiple model candidates across identical synthesized test suites: grounded questions, false premises,
          unanswerable prompts, and hidden prompt injections with Clopper-Pearson exact confidence intervals.
        </p>
      </div>

      {/* Info notice */}
      <div
        style={{
          padding: '14px 18px',
          backgroundColor: '#eff4ff',
          borderRadius: '8px',
          border: '1px solid #c7d2fe',
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-start',
          marginBottom: '24px',
          fontSize: '13px',
          color: '#1e40af',
          lineHeight: 1.5,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: '20px', color: '#3b82f6', marginTop: '1px' }}>
          info
        </span>
        <div>
          <strong>Deterministic replay & rate pacing: </strong>
          Simulated reference models execute locally in offline mode. Real OpenRouter endpoints are paced ~3 seconds apart.
          Any network or gateway timeout is recorded as missing evidence rather than a false failure.
        </div>
      </div>

      {/* Main Form Card */}
      <form
        onSubmit={handleSubmit}
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 4px 16px rgba(15, 23, 42, 0.04)',
          overflow: 'hidden',
        }}
      >
        {/* Section 1: Simulated Reference Models */}
        <div style={{ padding: '24px', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                1. Offline Simulated Reference Models
              </h2>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                Pre-calibrated reference behaviors that run deterministically in zero-network environments.
              </p>
            </div>
            <span style={{ fontSize: '11px', color: '#4f46e5', fontWeight: 600 }}>
              {selectedSim.length} selected
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
            {info.simulated.map((m) => {
              const isChecked = selectedSim.includes(m.id);
              return (
                <div
                  key={m.id}
                  onClick={() => handleSimToggle(m.id)}
                  style={{
                    padding: '14px 16px',
                    borderRadius: '8px',
                    border: `1.5px solid ${isChecked ? '#4f46e5' : '#e2e8f0'}`,
                    backgroundColor: isChecked ? '#f8faff' : '#ffffff',
                    cursor: 'pointer',
                    transition: 'all 150ms ease',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => handleSimToggle(m.id)}
                    style={{ marginTop: '3px', cursor: 'pointer' }}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <strong style={{ fontSize: '13px', color: '#0f172a' }}>{m.id}</strong>
                      <span className="tag t-sim" style={{ fontSize: '10px' }}>
                        Simulated
                      </span>
                    </div>
                    <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#64748b', lineHeight: 1.4 }}>
                      {m.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Section 2: Real OpenRouter Models */}
        <div style={{ padding: '24px', borderBottom: '1px solid #e2e8f0', backgroundColor: info.real_available ? '#ffffff' : '#f8fafc' }}>
          <div style={{ marginBottom: '12px' }}>
            <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
              2. Real Target Models (OpenRouter)
            </h2>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
              {info.real_available
                ? 'Comma-separated model identifiers to benchmark against reference models.'
                : `Live model calls are currently unavailable: ${info.reason || 'OPENROUTER_API_KEY is not set'}`}
            </p>
          </div>

          <input
            id="b-real"
            type="text"
            placeholder={info.suggested_real.join(', ') || 'e.g. meta-llama/llama-3.1-8b-instruct:free'}
            disabled={!info.real_available}
            value={realInput}
            onChange={(e) => setRealInput(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 14px',
              fontSize: '13px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: info.real_available ? '#ffffff' : '#f1f5f9',
              outline: 'none',
              fontFamily: 'var(--font-mono)',
            }}
          />

          {info.real_available && info.suggested_real.length > 0 && (
            <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>Quick Add:</span>
              {info.suggested_real.map((model) => (
                <button
                  key={model}
                  type="button"
                  onClick={() => handleAddSuggestedReal(model)}
                  style={{
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    backgroundColor: '#f1f5f9',
                    border: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    color: '#334155',
                  }}
                >
                  + {model}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Section 3: Focus & Suite Parameters */}
        <div style={{ padding: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px' }}>
          <div>
            <label htmlFor="b-focus" style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              Knowledge Focus Domain
            </label>
            <input
              id="b-focus"
              type="text"
              maxLength={300}
              placeholder="e.g. Returns and refunds, security policies"
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px',
                fontSize: '13px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                outline: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
              {['Returns & refunds', 'Authentication & tokens', 'Payment dispute', 'SQL injection'].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setFocus(preset)}
                  style={{
                    padding: '2px 6px',
                    fontSize: '10px',
                    borderRadius: '4px',
                    backgroundColor: '#f1f5f9',
                    border: '1px solid #e2e8f0',
                    color: '#475569',
                    cursor: 'pointer',
                  }}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="b-n" style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              Suite Size (Questions per model)
            </label>
            <select
              id="b-n"
              value={nTests}
              onChange={(e) => setNTests(Number(e.target.value))}
              style={{
                width: '100%',
                padding: '9px 12px',
                fontSize: '13px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                outline: 'none',
              }}
            >
              {[5, 10, 15, 20].map((v) => (
                <option key={v} value={v}>
                  {v} tests (balanced distribution)
                </option>
              ))}
            </select>
            <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#64748b' }}>
              Larger suites narrow Clopper-Pearson confidence bounds.
            </p>
          </div>

          <div>
            <label htmlFor="b-rep" style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              Repeats per Test (Consistency)
            </label>
            <select
              id="b-rep"
              value={repeats}
              onChange={(e) => setRepeats(Number(e.target.value))}
              style={{
                width: '100%',
                padding: '9px 12px',
                fontSize: '13px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                outline: 'none',
              }}
            >
              {[1, 2, 3].map((v) => (
                <option key={v} value={v}>
                  {v} repeat{v > 1 ? 's' : ''} (variance measurement)
                </option>
              ))}
            </select>
            <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#64748b' }}>
              Multiple passes verify non-deterministic model variance.
            </p>
          </div>
        </div>

        {/* Status error / message */}
        {status && (
          <div
            style={{
              padding: '12px 24px',
              backgroundColor: '#fff1f2',
              borderTop: '1px solid #fecdd3',
              color: '#e11d48',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              error
            </span>
            <span>{status}</span>
          </div>
        )}

        {/* Footer actions */}
        <div
          style={{
            padding: '16px 24px',
            backgroundColor: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div style={{ fontSize: '12px', color: '#64748b' }}>
            Estimated total calls: <strong>{(selectedSim.length + (realInput ? realInput.split(',').filter(Boolean).length : 0)) * nTests * repeats}</strong>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#4f46e5',
              color: '#ffffff',
              padding: '10px 20px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
              opacity: isSubmitting ? 0.7 : 1,
            }}
          >
            {isSubmitting ? (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: '18px', animation: 'spin 1.5s linear infinite' }}>
                  progress_activity
                </span>
                Starting Benchmark…
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  play_arrow
                </span>
                Launch Comparative Benchmark
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
