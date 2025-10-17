import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import type { Host } from '../api';

type HostFormProps = {
  initial?: Partial<Host>;
  onSubmit: (data: Partial<Host>) => Promise<void>;
  submitLabel?: string;
};

const HostForm = ({ initial, onSubmit, submitLabel = 'Save Host' }: HostFormProps) => {
  const [formState, setFormState] = useState({
    name: initial?.name ?? '',
    base_url: initial?.base_url ?? '',
    enabled: initial?.enabled ?? true
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setFormState({
      name: initial?.name ?? '',
      base_url: initial?.base_url ?? '',
      enabled: initial?.enabled ?? true
    });
  }, [initial?.name, initial?.base_url, initial?.enabled]);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = event.target;
    setFormState((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      await onSubmit(formState);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card">
      <div className="form-row">
        <div>
          <label htmlFor="name">Name</label>
          <input id="name" name="name" value={formState.name} onChange={handleChange} required />
        </div>
        <div>
          <label htmlFor="base_url">Base URL</label>
          <input
            id="base_url"
            name="base_url"
            value={formState.base_url}
            onChange={handleChange}
            placeholder="http://192.168.0.10:5000"
            required
          />
        </div>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '1rem' }}>
        <input
          type="checkbox"
          name="enabled"
          checked={formState.enabled}
          onChange={handleChange}
          style={{ width: 'auto' }}
        />
        Enabled
      </label>
      <button className="action-button" type="submit" disabled={loading} style={{ marginTop: '1.5rem' }}>
        {loading ? 'Saving…' : submitLabel}
      </button>
    </form>
  );
};

export default HostForm;
