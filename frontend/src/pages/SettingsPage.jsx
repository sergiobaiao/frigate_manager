import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api/client.js';

const SettingsPage = () => {
  const [form, setForm] = useState({
    telegram_bot_token: '',
    telegram_chat_id: '',
    container_filter: 'frigate',
    mention_user_ids: '',
    mention_name: '@sergiobaiao',
    check_interval_minutes: 10,
    timezone: 'America/Sao_Paulo',
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const load = async () => {
      const settings = await getSettings();
      setForm({
        ...settings,
        mention_user_ids: Array.isArray(settings.mention_user_ids)
          ? settings.mention_user_ids.join(',')
          : settings.mention_user_ids || '',
      });
    };
    load();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      const payload = {
        ...form,
        mention_user_ids: form.mention_user_ids
          .split(',')
          .map((id) => id.trim())
          .filter(Boolean),
      };
      await updateSettings(payload);
      setMessage('Configurações atualizadas com sucesso.');
    } catch (err) {
      console.error(err);
      setMessage('Não foi possível salvar as configurações.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2>Configurações</h2>
      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="telegram_bot_token">Telegram Bot Token</label>
            <input
              id="telegram_bot_token"
              className="input"
              value={form.telegram_bot_token}
              onChange={(e) => setForm({ ...form, telegram_bot_token: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="telegram_chat_id">Telegram Chat ID</label>
            <input
              id="telegram_chat_id"
              className="input"
              value={form.telegram_chat_id}
              onChange={(e) => setForm({ ...form, telegram_chat_id: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="container_filter">Filtro de Container</label>
            <input
              id="container_filter"
              className="input"
              value={form.container_filter}
              onChange={(e) => setForm({ ...form, container_filter: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="mention_user_ids">IDs de usuários (separados por vírgula)</label>
            <input
              id="mention_user_ids"
              className="input"
              value={form.mention_user_ids}
              onChange={(e) => setForm({ ...form, mention_user_ids: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="mention_name">Nome de menção</label>
            <input
              id="mention_name"
              className="input"
              value={form.mention_name}
              onChange={(e) => setForm({ ...form, mention_name: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="check_interval_minutes">Intervalo entre verificações (minutos)</label>
            <input
              id="check_interval_minutes"
              type="number"
              min="1"
              className="input"
              value={form.check_interval_minutes}
              onChange={(e) => setForm({ ...form, check_interval_minutes: Number(e.target.value) })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="timezone">Fuso horário</label>
            <input
              id="timezone"
              className="input"
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            />
          </div>
          <button className="button" type="submit" disabled={saving}>
            {saving ? 'Salvando...' : 'Salvar configurações'}
          </button>
        </form>
        {message && <p style={{ marginTop: '1rem' }}>{message}</p>}
      </div>
    </div>
  );
};

export default SettingsPage;
