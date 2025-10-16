import { useCallback, useEffect, useState } from 'react';

export const useAsync = (asyncFn, deps = [], options = {}) => {
  const { immediate = true } = options;
  const [status, setStatus] = useState('idle');
  const [value, setValue] = useState(null);
  const [error, setError] = useState(null);

  const execute = useCallback(async () => {
    setStatus('pending');
    setError(null);
    try {
      const result = await asyncFn();
      setValue(result);
      setStatus('success');
      return result;
    } catch (err) {
      setError(err);
      setStatus('error');
      throw err;
    }
  }, deps);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate]);

  return { execute, status, value, error };
};

export default useAsync;
