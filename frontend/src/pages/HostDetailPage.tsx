import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import FailureTable from '../components/FailureTable';
import { fetchHostLogs, fetchHostSummary } from '../api';
import api from '../api/client';

const HostDetailPage = () => {
  const params = useParams();
  const hostId = Number(params.id);
  const [serviceFilter, setServiceFilter] = useState<string>('');

  const summaryQuery = useQuery({
    queryKey: ['host-summary', hostId],
    queryFn: () => fetchHostSummary(hostId),
    enabled: Number.isFinite(hostId)
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
  const mediaBaseUrl = api.defaults.baseURL ?? (typeof window !== 'undefined' ? window.location.origin : '');

  const resolveMediaUrl = (path: string) => {
    try {
      return mediaBaseUrl ? new URL(path, mediaBaseUrl).toString() : path;
    } catch {
      return path;
    }
  };

  const latestEvidence = useMemo(() => {
    if (!latestFailure) {
      return { screenshots: [] as Array<{ url: string; label: string }>, logs: [] as Array<{ url: string; label: string }> };
    }
    const screenshots = [
      latestFailure.first_screenshot_path,
      latestFailure.second_screenshot_path
    ]
      .filter((value): value is string => Boolean(value))
      .map((value, index) => ({
        url: resolveMediaUrl(value),
        label: index === 0 ? 'Initial check' : 'Retry check'
      }));
    const logs = (latestFailure.log_files ?? []).map((value) => {
      const segments = value.split('/').filter(Boolean);
      const filename = segments[segments.length - 1] ?? 'log.txt';
      return {
        url: resolveMediaUrl(value),
        label: filename
      };
    });
    return { screenshots, logs };
  }, [latestFailure, mediaBaseUrl]);

  return (
    <div className="grid" style={{ gap: '1.5rem' }}>
      {host && (
        <div className="card">
          <h2 style={{ margin: 0 }}>{host.name}</h2>
          <p>{host.base_url}</p>
          <p>Status: {host.enabled ? <span className="badge">Enabled</span> : 'Disabled'}</p>
        </div>
      )}

      {latestFailure && (
        <section className="card">
          <div className="section-header" style={{ marginBottom: '1rem' }}>
            <h3>Latest evidence</h3>
            <span style={{ color: '#9ca3af' }}>
              Detected {new Date(latestFailure.created_at).toLocaleString('en-GB', { hour12: false })}
            </span>
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
