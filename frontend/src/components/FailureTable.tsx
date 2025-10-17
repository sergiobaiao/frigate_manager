import { FailureEvent } from '../api';

const formatDate = (date: string | null) => {
  if (!date) return '—';
  return new Date(date).toLocaleString('en-GB', { hour12: false });
};

type FailureTableProps = {
  failures: FailureEvent[];
};

const FailureTable = ({ failures }: FailureTableProps) => {
  if (!failures.length) {
    return <div className="card">No failures recorded.</div>;
  }

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Detected</th>
            <th>Estimated Start</th>
            <th>Failed Cameras</th>
            <th>Identifiers</th>
          </tr>
        </thead>
        <tbody>
          {failures.map((failure) => (
            <tr key={failure.id}>
              <td>{failure.id}</td>
              <td>{formatDate(failure.created_at)}</td>
              <td>{formatDate(failure.failure_start)}</td>
              <td>
                <span className="badge">{failure.failure_count}</span>
              </td>
              <td>{failure.camera_ids.join(', ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default FailureTable;
