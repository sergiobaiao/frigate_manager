import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import FailureTable from '../components/FailureTable';
import StatsCard from '../components/StatsCard';
import { fetchFailureStats, fetchFailures } from '../api';

const DashboardPage = () => {
  const failuresQuery = useQuery({ queryKey: ['failures'], queryFn: () => fetchFailures() });
  const statsQuery = useQuery({ queryKey: ['stats'], queryFn: fetchFailureStats });

  const chartData = useMemo(() => {
    if (!failuresQuery.data) return [];
    const map = new Map<string, number>();
    failuresQuery.data.forEach((failure) => {
      const day = failure.created_at.split('T')[0];
      map.set(day, (map.get(day) ?? 0) + failure.failure_count);
    });
    return Array.from(map.entries()).map(([date, total]) => ({ date, total }));
  }, [failuresQuery.data]);

  return (
    <div className="grid" style={{ gap: '2rem' }}>
      <div className="grid three-columns">
        <StatsCard
          label="Recorded failures"
          value={failuresQuery.data?.length ?? 0}
          footer="Total events captured"
        />
        <StatsCard
          label="Impacted cameras"
          value={failuresQuery.data?.reduce((sum, item) => sum + item.failure_count, 0) ?? 0}
        />
        <StatsCard
          label="Active hosts"
          value={statsQuery.data?.length ?? 0}
          footer="Currently monitored"
        />
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Failures by day</h2>
        <div className="chart-container">
          <ResponsiveContainer>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#1f2937', border: 'none' }} />
              <Area type="monotone" dataKey="total" stroke="#818cf8" fill="url(#colorTotal)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <section>
        <div className="section-header">
          <h2>Latest failures</h2>
        </div>
        <FailureTable failures={failuresQuery.data ?? []} />
      </section>
    </div>
  );
};

export default DashboardPage;
