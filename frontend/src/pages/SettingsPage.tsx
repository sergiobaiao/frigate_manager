import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Config, captureTestScreenshot, fetchConfig, updateConfig } from '../api';
import TagInput from '../components/TagInput';

const SettingsPage = () => {
  const queryClient = useQueryClient();
  const configQuery = useQuery({ queryKey: ['config'], queryFn: fetchConfig });
  const config = configQuery.data;
  const mutation = useMutation({
    mutationFn: (payload: Partial<Config>) => updateConfig(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config'] })
  });

  const [formState, setFormState] = useState<Partial<Config>>({});
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const [testUrl, setTestUrl] = useState('');
  const [testScreenshot, setTestScreenshot] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  useEffect(() => {
    if (config?.MENTION_USER_IDS !== undefined) {
      const ids = config.MENTION_USER_IDS.split(',')
        .map((value) => value.trim())
        .filter(Boolean);
      setMentionIds(ids);
    }
  }, [config?.MENTION_USER_IDS]);

  useEffect(() => {
    if (config?.USE_GPU_FOR_OCR !== undefined) {
      setFormState((previous) =>
        previous.USE_GPU_FOR_OCR === undefined
          ? { ...previous, USE_GPU_FOR_OCR: config.USE_GPU_FOR_OCR }
          : previous
      );
    }
  }, [config?.USE_GPU_FOR_OCR]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload: Partial<Config> = {
      ...formState,
      MENTION_USER_IDS: mentionIds.join(',')
    };
    await mutation.mutateAsync(payload);
  };

  const handleTestScreenshot = async () => {
    if (!testUrl) {
      setTestError('Please enter a URL to test.');
      return;
    }
    setIsTesting(true);
    setTestError(null);
    setTestScreenshot(null);
    try {
      const response = await captureTestScreenshot(testUrl);
      setTestScreenshot(response.image_data_url);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTestError(detail ?? 'Unable to capture a screenshot for the provided URL.');
    } finally {
      setIsTesting(false);
    }
  };

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
          <TagInput
            value={mentionIds}
            onChange={(values) => {
              setMentionIds(values);
              setFormState((prev) => ({ ...prev, MENTION_USER_IDS: values.join(',') }));
            }}
            placeholder="Enter IDs and press Enter"
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
        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={formState.USE_GPU_FOR_OCR ?? config?.USE_GPU_FOR_OCR ?? false}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, USE_GPU_FOR_OCR: event.target.checked }))
              }
            />
            Enable GPU acceleration for camera recognition
          </label>
          <p className="hint-text" style={{ marginTop: '0.25rem' }}>
            When enabled, Frigate Manager will attempt to use GPU resources for OCR-based camera
            failure detection. Make sure the container has access to GPU drivers and runtimes so
            the OCR backend can initialise successfully.
          </p>
        </div>
        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={formState.DEBUG_MODE ?? config?.DEBUG_MODE ?? false}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, DEBUG_MODE: event.target.checked }))
              }
            />
            Enable debug mode
          </label>
          <p className="hint-text" style={{ marginTop: '0.25rem' }}>
            When enabled, Frigate Manager stores Playwright trace files for each check so you can
            review the exact browser actions under <code>data/traces</code>.
          </p>
        </div>
        <button type="submit" className="action-button" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save configuration'}
        </button>
      </form>
      <hr style={{ margin: '2rem 0' }} />
      <div>
        <h3>Test dashboard screenshot</h3>
        <p style={{ marginBottom: '1rem' }}>
          Provide a webpage URL to verify that Frigate Manager can capture live dashboard screenshots.
        </p>
        <div className="form-row" style={{ gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '0.75rem' }}>
          <input
            type="url"
            placeholder="https://example.com"
            value={testUrl}
            onChange={(event) => setTestUrl(event.target.value)}
          />
          <button
            type="button"
            className="action-button"
            style={{ whiteSpace: 'nowrap' }}
            onClick={handleTestScreenshot}
            disabled={isTesting}
          >
            {isTesting ? 'Capturing…' : 'Run test'}
          </button>
        </div>
        {testError && (
          <p className="error-text" style={{ marginTop: '0.75rem' }}>
            {testError}
          </p>
        )}
        {testScreenshot && (
          <div style={{ marginTop: '1.5rem' }}>
            <p style={{ marginBottom: '0.5rem' }}>Screenshot preview</p>
            <img
              src={testScreenshot}
              alt="Test screenshot preview"
              style={{ width: '100%', borderRadius: '0.5rem', border: '1px solid var(--muted-border-color)' }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage;
