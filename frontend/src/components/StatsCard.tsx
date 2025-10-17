import { ReactNode } from 'react';

type StatsCardProps = {
  label: string;
  value: ReactNode;
  footer?: ReactNode;
};

const StatsCard = ({ label, value, footer }: StatsCardProps) => (
  <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
    <span style={{ color: '#9ca3af', fontSize: '0.85rem' }}>{label}</span>
    <strong style={{ fontSize: '1.75rem' }}>{value}</strong>
    {footer && <span style={{ fontSize: '0.9rem', color: '#cbd5f5' }}>{footer}</span>}
  </div>
);

export default StatsCard;
