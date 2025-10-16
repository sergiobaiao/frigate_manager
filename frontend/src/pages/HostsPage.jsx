import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createHost,
  deleteHost,
  getHosts,
  triggerHostCheck,
  updateHost,
} from '../api/client.js';

const emptyForm = {
  name: '',
  address: 'http://',
  notes: '',
};

const HostsPage = () => {
  const [hosts, setHosts] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadHosts = async () => {
    try {
      const data = await getHosts();
      setHosts(data);
    } catch (err) {
      console.error(err);
      setError('Erro ao carregar hosts');
    }
  };

  useEffect(() => {
    loadHosts();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (editingId) {
        await updateHost(editingId, form);
      } else {
        await createHost(form);
      }
      setForm(emptyForm);
      setEditingId(null);
      await loadHosts();
    } catch (err) {
      console.error(err);
      setError('Não foi possível salvar o host. Verifique os dados informados.');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (host) => {
    setEditingId(host.id);
    setForm({ name: host.name, address: host.address, notes: host.notes || '' });
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Deseja remover este host?')) return;
    await deleteHost(id);
    await loadHosts();
  };

  const handleTrigger = async (id) => {
    setLoading(true);
    try {
      await triggerHostCheck(id);
      await loadHosts();
      alert('Verificação manual iniciada. Consulte o histórico para mais detalhes.');
    } catch (err) {
      console.error(err);
      alert('Erro ao iniciar verificação manual.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Hosts monitorados</h2>
      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3>{editingId ? 'Editar Host' : 'Adicionar Host'}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">Nome</label>
            <input
              id="name"
              className="input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="address">Endereço</label>
            <input
              id="address"
              className="input"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="notes">Notas</label>
            <textarea
              id="notes"
              className="textarea"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
          <button className="button" type="submit" disabled={loading}>
            {loading ? 'Salvando...' : editingId ? 'Atualizar' : 'Adicionar'}
          </button>
          {editingId && (
            <button
              type="button"
              className="button"
              style={{ marginLeft: '1rem', background: '#64748b', color: 'white' }}
              onClick={() => {
                setEditingId(null);
                setForm(emptyForm);
              }}
            >
              Cancelar
            </button>
          )}
        </form>
        {error && <p style={{ color: '#f97316' }}>{error}</p>}
      </div>

      <div className="card">
        <h3>Lista de hosts</h3>
        {hosts.length === 0 ? (
          <p>Nenhum host cadastrado.</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Endereço</th>
                  <th>Notas</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {hosts.map((host) => (
                  <tr key={host.id}>
                    <td>{host.name}</td>
                    <td>{host.address}</td>
                    <td>{host.notes}</td>
                    <td>
                      <button className="button" onClick={() => handleEdit(host)}>
                        Editar
                      </button>{' '}
                      <button
                        className="button"
                        style={{ background: '#f97316' }}
                        onClick={() => handleTrigger(host.id)}
                      >
                        Verificar agora
                      </button>{' '}
                      <button
                        className="button"
                        style={{ background: '#ef4444' }}
                        onClick={() => handleDelete(host.id)}
                      >
                        Remover
                      </button>{' '}
                      <Link className="button" style={{ textDecoration: 'none' }} to={`/hosts/${host.id}`}>
                        Detalhes
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default HostsPage;
