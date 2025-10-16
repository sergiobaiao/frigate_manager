import { useEffect, useState } from 'react';
import { Bar, Line } from 'react-chartjs-2';
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  BarElement,
  Title,
  Tooltip,
} from 'chart.js';
import { fetchStatus, fetchSummary } from '../api/client.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend);

const DashboardPage = () => {
  const [status, setStatus] = useState({ statuses: [] });
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [statusResponse, summaryResponse] = await Promise.all([fetchStatus(), fetchSummary()]);
        setStatus(statusResponse);
        setSummary(summaryResponse);
      } catch (error) {
        console.error('Erro ao carregar dashboard', error);
      }
    };

    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  const renderStatusCards = () => {
    if (!status.statuses?.length) {
      return <p>Nenhum histórico disponível ainda.</p>;
    }

    return (
      <div className="card-grid">
        {status.statuses.map((entry) => (
          <div className="card" key={`${entry.host_id}-${entry.timestamp}`}>
            <h3>{entry.host_name}</h3>
            <p>
              Último teste: {new Date(entry.timestamp).toLocaleString('pt-BR')} <br />
              Status:{' '}
              <span className={`status-pill ${entry.status}`}>
                {entry.status.toUpperCase()}
              </span>
            </p>
            <p>
              Câmeras em falha: {entry.failing_count}
              {entry.failing_cameras?.length ? (
                <>
                  <br />Câmeras: {entry.failing_cameras.join(', ')}
                </>
              ) : null}
            </p>
          </div>
        ))}
      </div>
    );
  };

  const renderCharts = () => {
    if (!summary) {
      return null;
    }

    const hostMetrics = summary.hosts || [];
    const labels = hostMetrics.map((item) => item.host.name);
    const failureCounts = hostMetrics.map((item) => item.totals.failures);
    const checks = hostMetrics.map((item) => item.totals.total_checks);

    const failuresChart = {
      labels,
      datasets: [
        {
          label: 'Falhas',
          data: failureCounts,
          backgroundColor: 'rgba(239, 68, 68, 0.6)',
        },
        {
          label: 'Testes',
          data: checks,
          backgroundColor: 'rgba(56, 189, 248, 0.6)',
        },
      ],
    };

    const timelineEntries = hostMetrics
      .flatMap((item) => item.history)
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
      .slice(-20);

    const timelineData = {
      labels: timelineEntries.map((entry) => new Date(entry.timestamp).toLocaleString('pt-BR')),
      datasets: [
        {
          label: 'Falhas recentes',
          data: timelineEntries.map((entry) => (entry.status === 'failure' ? entry.failing_count || 1 : 0)),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.3)',
        },
      ],
    };

    return (
      <div className="card-grid" style={{ marginTop: '2rem' }}>
        <div className="chart-card">
          <h3>Falhas por host</h3>
          <Bar data={failuresChart} options={{ responsive: true, plugins: { legend: { position: 'bottom' } } }} />
        </div>
        <div className="chart-card">
          <h3>Timeline de falhas recentes</h3>
          <Line data={timelineData} options={{ responsive: true, plugins: { legend: { display: false } } }} />
        </div>
      </div>
    );
  };

  return (
    <div>
      <h2>Visão Geral</h2>
      {renderStatusCards()}
      {renderCharts()}
    </div>
  );
};

export default DashboardPage;
