import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Config, fetchConfig, updateConfig } from '../api';

const SettingsPage = () => {
  const queryClient = useQueryClient();
  const configQuery = useQuery({ queryKey: ['config'], queryFn: fetchConfig });
  const mutation = useMutation({
    mutationFn: (payload: Partial<Config>) => updateConfig(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config'] })
  });

  const [formState, setFormState] = useState<Partial<Config>>({});

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await mutation.mutateAsync(formState);
  };

  const config = configQuery.data;

  return (
    <div className="card" style={{ maxWidth: 720 }}>
      <h2>Configuration</h2>
      <p>Update notification channels, schedule intervals, and mention details.</p>
      <form className="grid" style={{ gap: '1rem', marginTop: '1.5rem' }} onSubmit={handleSubmit}>
        <div>
          <label>Telegram Bot Token</label>
          <input
            defaultValue={config?.TELEGRAM_BOT_TOKEN}
            onChange={(event) => setFormState((prev) => ({ ...prev, TELEGRAM_BOT_TOKEN: event.target.value }))}
          />
        </div>
        <div>
          <label>Telegram Chat ID</label>
          <input
            defaultValue={config?.TELEGRAM_CHAT_ID}
            onChange={(event) => setFormState((prev) => ({ ...prev, TELEGRAM_CHAT_ID: event.target.value }))}
          />
        </div>
        <div>
          <label>Mention User IDs</label>
          <input
            defaultValue={config?.MENTION_USER_IDS}
            onChange={(event) => setFormState((prev) => ({ ...prev, MENTION_USER_IDS: event.target.value }))}
          />
        </div>
        <div>
          <label>Mention name</label>
          <input
            defaultValue={config?.MENTION_NAME}
            onChange={(event) => setFormState((prev) => ({ ...prev, MENTION_NAME: event.target.value }))}
          />
        </div>
        <div>
          <label>Container filter</label>
          <input
            defaultValue={config?.CONTAINER_FILTER}
            onChange={(event) => setFormState((prev) => ({ ...prev, CONTAINER_FILTER: event.target.value }))}
          />
        </div>
        <div className="form-row" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div>
            <label>Check interval (minutes)</label>
            <input
              type="number"
              min={1}
              defaultValue={config?.CHECK_INTERVAL_MINUTES ?? 10}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, CHECK_INTERVAL_MINUTES: Number(event.target.value) }))
              }
            />
          </div>
          <div>
            <label>Retry delay (minutes)</label>
            <input
              type="number"
              min={1}
              defaultValue={config?.RETRY_DELAY_MINUTES ?? 5}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, RETRY_DELAY_MINUTES: Number(event.target.value) }))
              }
            />
          </div>
        </div>
        <button type="submit" className="action-button" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save configuration'}
        </button>
      </form>
    </div>
  );
};

export default SettingsPage;
