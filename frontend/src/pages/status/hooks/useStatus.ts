import { useAsync } from '../../../hooks/useAsync';
import { getStatus } from '../endpoints/status';

export function useStatus(enabled: boolean) {
  return useAsync(getStatus, [], { enabled });
}
