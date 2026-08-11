import { useAsync } from '../../../hooks/useAsync';
import { getRoots } from '../endpoints/roots';

/** Read only when the tab is opened; nobody lands here first. */
export function useRoots(enabled: boolean) {
  return useAsync(getRoots, [], { enabled });
}
