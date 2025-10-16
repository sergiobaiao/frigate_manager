import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Bar } from 'react-chartjs-2';
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  BarElement,
  Tooltip,
} from 'chart.js';
import { fetchHostHistory, fetchLogs } from '../api/client.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, Legend, Tooltip);

const buildDataset = (aggregated) => {
  const labels = aggregated.by_day?.map((row) => row.date) ?? [];
  return {
    labels,
    datasets: [
      {
        label: 'Falhas',
        data: aggregated.by_day?.map((row) => row.failures) ?? [],
        backgroundColor: 'rgba(239, 68, 68, 0.6)',
      },
      {
        label: 'Testes',
        data: aggregated.by_day?.map((row) => row.checks) ?? [],
        backgroundColor: 'rgba(59, 130, 246, 0.6)',
      },
    ],
  };
};

const LogTable = ({ service, columns = [], rows = [] }) => {
  const [filters, setFilters] = useState({});

  const filteredRows = useMemo(() => {
    return rows.filter((row) =>
      Object.entries(filters).every(([key, value]) =>
        value ? row[key].toLowerCase().includes(value.toLowerCase()) : true,
      ),
    );
  }, [filters, rows]);

  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <h3>Logs - {service}</h3>
      <div className="filters">
        {columns.map((column) => (
          <input
            key={column}
            className="input"
            placeholder={`Filtrar ${column}`}
            value={filters[column] || ''}
            onChange={(event) => setFilters({ ...filters, [column]: event.target.value })}
          />
        ))}
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row, index) => (
              <tr key={`${service}-${index}`}>
                {columns.map((column) => (
                  <td key={column}>{row[column]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const HostDetailPage = () => {
  const { hostId } = useParams();
  const [history, setHistory] = useState({ entries: [], aggregated: {} });
  const [logs, setLogs] = useState({ logs: {} });

  useEffect(() => {
    const load = async () => {
      const [historyResponse, logsResponse] = await Promise.all([
        fetchHostHistory(hostId),
        fetchLogs(hostId),
      ]);
      setHistory(historyResponse);
      setLogs(logsResponse);
    };
    load();
  }, [hostId]);

  const aggregated = history.aggregated || { by_day: [], by_camera: {} };
  const dataset = buildDataset(aggregated);

  return (
    <div>
      <h2>Detalhes do host {logs.host?.name}</h2>
      <div className="card-grid">
        <div className="card">
          <h3>Métricas</h3>
          <p className="metric">Total de testes: {aggregated.by_day?.reduce((acc, row) => acc + row.checks, 0) ?? 0}</p>
          <p className="metric">
            Total de falhas: {aggregated.by_day?.reduce((acc, row) => acc + row.failures, 0) ?? 0}
          </p>
          <p className="metric">
            Câmeras mais afetadas:{' '}
            {Object.entries(aggregated.by_camera || {})
              .sort((a, b) => b[1] - a[1])
              .map(([camera, count]) => (
                <span key={camera} className="badge">
                  #{camera}: {count}
                </span>
              ))}
          </p>
        </div>
        <div className="chart-card">
          <h3>Falhas por dia</h3>
          <Bar data={dataset} options={{ responsive: true, plugins: { legend: { position: 'bottom' } } }} />
        </div>
      </div>

      <div className="card" style={{ marginTop: '2rem' }}>
        <h3>Histórico de testes</h3>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th>Status</th>
                <th>Câmeras em falha</th>
                <th>Início estimado</th>
              </tr>
            </thead>
            <tbody>
              {history.entries?.map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.timestamp).toLocaleString('pt-BR')}</td>
                  <td>
                    <span className={`status-pill ${entry.status}`}>{entry.status.toUpperCase()}</span>
                  </td>
                  <td>{entry.failing_cameras?.join(', ') || '-'}</td>
                  <td>
                    {entry.failure_started_at
                      ? new Date(entry.failure_started_at).toLocaleString('pt-BR')
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {logs.logs &&
        Object.entries(logs.logs).map(([service, data]) => (
          <LogTable key={service} service={service} columns={data.columns} rows={data.rows} />
        ))}
    </div>
  );
};

export default HostDetailPage;
