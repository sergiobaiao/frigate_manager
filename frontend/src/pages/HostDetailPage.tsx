import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';

import FailureTable from '../components/FailureTable';
import { fetchHostLogs, fetchHostSummary, triggerHostCheck } from '../api';
import api from '../api/client';

const HostDetailPage = () => {
  const params = useParams();
  const hostId = Number(params.id);
  const [serviceFilter, setServiceFilter] = useState<string>('');
  const [manualError, setManualError] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ['host-summary', hostId],
    queryFn: () => fetchHostSummary(hostId),
    enabled: Number.isFinite(hostId),
    refetchInterval: (data) => {
      const status = data?.current_check?.status ?? data?.latest_check?.status;
      return status && (status === 'pending' || status === 'running') ? 2000 : false;
    }
  });

  const logsQuery = useQuery({
    queryKey: ['host-logs', hostId, serviceFilter],
    queryFn: () => fetchHostLogs(hostId, serviceFilter || undefined),
    enabled: Number.isFinite(hostId)
  });

  const services = useMemo(() => {
    const raw = logsQuery.data ?? [];
    return Array.from(new Set(raw.map((entry) => entry.service))).filter(Boolean);
  }, [logsQuery.data]);

  const host = summaryQuery.data?.host;
  const failures = summaryQuery.data?.failures ?? [];
  const latestFailure = failures[0];
  const latestMedia = summaryQuery.data?.latest_media;
  const currentCheck = summaryQuery.data?.current_check ?? null;
  const latestCheck = summaryQuery.data?.latest_check ?? null;
  const displayCheck = currentCheck ?? latestCheck;
  const mediaBaseUrl = api.defaults.baseURL ?? (typeof window !== 'undefined' ? window.location.origin : '');
  const latestLogEntry = displayCheck?.log?.length ? displayCheck.log[displayCheck.log.length - 1] : null;

  const triggerCheckMutation = useMutation({
    mutationFn: () => triggerHostCheck(hostId),
    onMutate: () => {
      setManualError(null);
    },
    onSuccess: () => {
      summaryQuery.refetch();
    },
    onError: (error: unknown) => {
      if (error instanceof Error) {
        setManualError(error.message);
      } else {
        setManualError('Failed to start check.');
      }
    }
  });

  const resolveMediaUrl = (path: string) => {
    try {
      return mediaBaseUrl ? new URL(path, mediaBaseUrl).toString() : path;
    } catch {
      return path;
    }
  };

  const latestEvidence = useMemo(() => {
    const screenshots = (latestMedia?.screenshots ?? []).map((item) => ({
      url: resolveMediaUrl(item.url),
      label: item.label
    }));
    const logs = (latestMedia?.logs ?? []).map((item) => ({
      url: resolveMediaUrl(item.url),
      label: item.label
    }));
    return { screenshots, logs, capturedAt: latestMedia?.captured_at ?? null };
  }, [latestMedia, mediaBaseUrl]);

  const hasEvidence = latestEvidence.screenshots.length > 0 || latestEvidence.logs.length > 0;
  const isCheckActive = currentCheck ? ['pending', 'running'].includes(currentCheck.status) : false;
  const manualCheckDisabled = triggerCheckMutation.isLoading || !Number.isFinite(hostId) || isCheckActive;

  const handleManualCheck = () => {
    if (!Number.isFinite(hostId) || triggerCheckMutation.isLoading) {
      return;
    }
    triggerCheckMutation.mutate();
  };

  const renderTimestamp = (value?: string | null) => {
    if (!value) return '—';
    return new Date(value).toLocaleString('en-GB', { hour12: false });
  };

  const evidenceSubtitle = useMemo(() => {
    if (latestFailure) {
      return `Detected ${new Date(latestFailure.created_at).toLocaleString('en-GB', { hour12: false })}`;
    }
    if (latestEvidence.capturedAt) {
      return `Captured ${new Date(latestEvidence.capturedAt).toLocaleString('en-GB', { hour12: false })}`;
    }
    if (displayCheck?.started_at) {
      return `Last check ${new Date(displayCheck.started_at).toLocaleString('en-GB', { hour12: false })}`;
    }
    return 'Most recent check';
  }, [displayCheck?.started_at, latestEvidence.capturedAt, latestFailure]);

  return (
    <div className="grid" style={{ gap: '1.5rem' }}>
      {host && (
        <div className="card host-card">
          <div className="host-card-info">
            <h2 style={{ margin: 0 }}>{host.name}</h2>
            <p>{host.base_url}</p>
            <p>
              Status:{' '}
              {host.enabled ? <span className="badge">Enabled</span> : <span className="badge badge-muted">Disabled</span>}
            </p>
          </div>
          <div className="host-card-actions">
            <button
              type="button"
              className="action-button"
              onClick={handleManualCheck}
              disabled={manualCheckDisabled}
            >
              {triggerCheckMutation.isLoading || isCheckActive ? 'Checking…' : 'Force check'}
            </button>
            {isCheckActive && (
              <span className="hint-text">Check in progress. This view refreshes automatically.</span>
            )}
            {!isCheckActive && latestLogEntry && (
              <span className="hint-text">Last update: {latestLogEntry.message}</span>
            )}
            {manualError && <span className="error-text">{manualError}</span>}
          </div>
        </div>
      )}

      <section className="card">
        <div className="section-header" style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Debug</h3>
          {displayCheck ? (
            <span className={`status-chip status-${displayCheck.status}`}>
              {displayCheck.status}
            </span>
          ) : (
            <span className="status-chip status-idle">idle</span>
          )}
        </div>
        {currentCheck ? (
          <p className="hint-text" style={{ marginTop: '-0.5rem', marginBottom: '1rem' }}>
            Tracking a {currentCheck.trigger} check started {renderTimestamp(currentCheck.started_at ?? currentCheck.created_at)}.
          </p>
        ) : (
          latestCheck && (
            <p className="hint-text" style={{ marginTop: '-0.5rem', marginBottom: '1rem' }}>
              Showing the most recent {latestCheck.trigger} check from {renderTimestamp(latestCheck.started_at ?? latestCheck.created_at)}.
            </p>
          )
        )}
        {displayCheck ? (
          <div className="debug-summary">
            <div className="debug-meta">
              <p>
                <strong>Trigger:</strong> {displayCheck.trigger}
              </p>
              <p>
                <strong>Summary:</strong> {displayCheck.summary ?? '—'}
              </p>
              <p>
                <strong>Started:</strong> {renderTimestamp(displayCheck.started_at ?? displayCheck.created_at)}
              </p>
              <p>
                <strong>Finished:</strong> {renderTimestamp(displayCheck.finished_at)}
              </p>
            </div>
            <div className="debug-log">
              {displayCheck.log?.length ? (
                displayCheck.log.map((entry) => (
                  <div key={`${entry.timestamp}-${entry.message}`} className="debug-log-entry">
                    <span className="debug-log-time">{renderTimestamp(entry.timestamp)}</span>
                    <span className="debug-log-message">{entry.message}</span>
                  </div>
                ))
              ) : (
                <p style={{ color: '#9ca3af' }}>No log entries recorded for this check.</p>
              )}
            </div>
          </div>
        ) : (
          <p style={{ color: '#9ca3af' }}>
            No checks have run for this host yet. Trigger one to begin collecting debug data.
          </p>
        )}
      </section>

      {hasEvidence && (
        <section className="card">
          <div className="section-header" style={{ marginBottom: '1rem' }}>
            <h3>Latest evidence</h3>
            <span style={{ color: '#9ca3af' }}>{evidenceSubtitle}</span>
          </div>
          <div className="evidence-grid">
            <div>
              <h4 style={{ marginTop: 0 }}>Screenshots</h4>
              {latestEvidence.screenshots.length ? (
                <div className="screenshot-grid">
                  {latestEvidence.screenshots.map((shot) => (
                    <a key={shot.label} href={shot.url} target="_blank" rel="noreferrer" className="screenshot-preview">
                      <img src={shot.url} alt={shot.label} />
                      <span>{shot.label}</span>
                    </a>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#9ca3af' }}>No screenshots available.</p>
              )}
            </div>
            <div>
              <h4 style={{ marginTop: 0 }}>Log files</h4>
              {latestEvidence.logs.length ? (
                <ul className="file-list">
                  {latestEvidence.logs.map((file) => (
                    <li key={file.url}>
                      <a href={file.url} target="_blank" rel="noreferrer">
                        {file.label}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ color: '#9ca3af' }}>No log files attached.</p>
              )}
            </div>
          </div>
        </section>
      )}

      <section>
        <div className="section-header">
          <h3>Failure history</h3>
        </div>
        <FailureTable failures={failures} />
      </section>

      <section className="card">
        <div className="section-header" style={{ marginBottom: '1rem' }}>
          <h3>Log entries</h3>
          <select value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)} style={{ width: '200px' }}>
            <option value="">All services</option>
            {services.map((service) => (
              <option key={service} value={service}>
                {service}
              </option>
            ))}
          </select>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Service</th>
                <th>Level</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {(logsQuery.data ?? []).map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.timestamp ? new Date(entry.timestamp).toLocaleString('en-GB', { hour12: false }) : '—'}</td>
                  <td>{entry.service}</td>
                  <td>{entry.level ?? '—'}</td>
                  <td>{entry.message ?? JSON.stringify(entry.raw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default HostDetailPage;
