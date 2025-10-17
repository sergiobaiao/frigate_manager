import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import FailureTable from '../components/FailureTable';
import { fetchHostLogs, fetchHostSummary } from '../api';

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

  return (
    <div className="grid" style={{ gap: '1.5rem' }}>
      {host && (
        <div className="card">
          <h2 style={{ margin: 0 }}>{host.name}</h2>
          <p>{host.base_url}</p>
          <p>Status: {host.enabled ? <span className="badge">Enabled</span> : 'Disabled'}</p>
        </div>
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
