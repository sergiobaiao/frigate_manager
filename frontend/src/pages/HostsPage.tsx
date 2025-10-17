import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import HostForm from '../components/HostForm';
import { Host, createHost, deleteHost, fetchHosts, updateHost } from '../api';

const HostsPage = () => {
  const queryClient = useQueryClient();
  const hostsQuery = useQuery({ queryKey: ['hosts'], queryFn: fetchHosts });
  const [selectedHostId, setSelectedHostId] = useState<number | null>(null);

  const createMutation = useMutation({
    mutationFn: createHost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Host> }) => updateHost(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteHost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] });
    }
  });

  const selectedHost = hostsQuery.data?.find((host) => host.id === selectedHostId) ?? null;

  return (
    <div className="grid two-columns">
      <div className="card">
        <div className="section-header">
          <h2>Monitored hosts</h2>
          <span className="badge">{hostsQuery.data?.length ?? 0}</span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Base URL</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {(hostsQuery.data ?? []).map((host) => (
              <tr key={host.id}>
                <td>
                  <Link to={`/hosts/${host.id}`}>{host.name}</Link>
                </td>
                <td>{host.base_url}</td>
                <td>{host.enabled ? <span className="badge">Enabled</span> : 'Disabled'}</td>
                <td style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="action-button" style={{ padding: '0.25rem 0.75rem' }} onClick={() => setSelectedHostId(host.id)}>
                    Edit
                  </button>
                  <button
                    className="action-button"
                    style={{ padding: '0.25rem 0.75rem', background: '#dc2626' }}
                    onClick={() => deleteMutation.mutate(host.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h2>{selectedHost ? `Edit ${selectedHost.name}` : 'Add host'}</h2>
        <HostForm
          initial={selectedHost ?? undefined}
          submitLabel={selectedHost ? 'Update Host' : 'Add Host'}
          onSubmit={async (data) => {
            if (selectedHost) {
              await updateMutation.mutateAsync({ id: selectedHost.id, data });
            } else {
              await createMutation.mutateAsync(data);
            }
            setSelectedHostId(null);
          }}
        />
      </div>
    </div>
  );
};

export default HostsPage;
