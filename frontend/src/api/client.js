import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

export const getHosts = async () => {
  const { data } = await api.get('/api/hosts');
  return data;
};

export const createHost = async (payload) => {
  const { data } = await api.post('/api/hosts', payload);
  return data;
};

export const updateHost = async (id, payload) => {
  const { data } = await api.put(`/api/hosts/${id}`, payload);
  return data;
};

export const deleteHost = async (id) => {
  await api.delete(`/api/hosts/${id}`);
};

export const triggerHostCheck = async (id) => {
  const { data } = await api.post(`/api/hosts/${id}/trigger`);
  return data;
};

export const getSettings = async () => {
  const { data } = await api.get('/api/settings');
  return data;
};

export const updateSettings = async (payload) => {
  const { data } = await api.put('/api/settings', payload);
  return data;
};

export const fetchSummary = async () => {
  const { data } = await api.get('/api/history/summary');
  return data;
};

export const fetchHostHistory = async (hostId) => {
  const { data } = await api.get(`/api/history/host/${hostId}`);
  return data;
};

export const fetchLogs = async (hostId) => {
  const { data } = await api.get(`/api/logs/${hostId}`);
  return data;
};

export const fetchStatus = async () => {
  const { data } = await api.get('/api/status');
  return data;
};

export default api;
