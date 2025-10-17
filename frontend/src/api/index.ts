import api from './client';

export type Host = {
  id: number;
  name: string;
  base_url: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type FailureEvent = {
  id: number;
  host_id: number;
  failure_count: number;
  camera_ids: string[];
  failure_start: string | null;
  first_screenshot_path: string | null;
  second_screenshot_path: string | null;
  log_files: string[];
  created_at: string;
};

export type Config = {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  CONTAINER_FILTER: string;
  MENTION_USER_IDS: string;
  MENTION_NAME: string;
  CHECK_INTERVAL_MINUTES: number;
  RETRY_DELAY_MINUTES: number;
};

export const fetchHosts = async (): Promise<Host[]> => {
  const { data } = await api.get<Host[]>('/hosts');
  return data;
};

export const createHost = async (payload: Partial<Host>): Promise<Host> => {
  const { data } = await api.post<Host>('/hosts', payload);
  return data;
};

export const updateHost = async (id: number, payload: Partial<Host>): Promise<Host> => {
  const { data } = await api.put<Host>(`/hosts/${id}`, payload);
  return data;
};

export const deleteHost = async (id: number) => {
  await api.delete(`/hosts/${id}`);
};

export const fetchFailures = async (hostId?: number): Promise<FailureEvent[]> => {
  const { data } = await api.get<FailureEvent[]>('/failures', {
    params: {
      host_id: hostId
    }
  });
  return data;
};

export const fetchFailureStats = async () => {
  const { data } = await api.get('/failures/stats');
  return data as Array<{
    host_id: number;
    total_failures: number;
    total_cameras_impacted: number;
    last_failure: string | null;
  }>;
};

export const fetchConfig = async (): Promise<Config> => {
  const { data } = await api.get<Config>('/config');
  return data;
};

export const updateConfig = async (payload: Partial<Config>): Promise<Config> => {
  const { data } = await api.put<Config>('/config', payload);
  return data;
};

export const fetchHostSummary = async (id: number) => {
  const { data } = await api.get(`/failures/host/${id}/summary`);
  return data as {
    host: Host;
    failures: FailureEvent[];
    latest_media: {
      screenshots: Array<{ url: string; label: string }>;
      logs: Array<{ url: string; label: string }>;
      captured_at: string | null;
    };
  };
};

export const fetchHostLogs = async (id: number, service?: string) => {
  const { data } = await api.get(`/failures/host/${id}/logs`, {
    params: {
      service
    }
  });
  return data as Array<{
    id: number;
    service: string;
    timestamp: string | null;
    level: string | null;
    message: string | null;
    raw: Record<string, unknown>;
  }>;
};
