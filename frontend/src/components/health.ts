import type { OverviewResponse } from '../api/types';

export interface Verdict {
  band: 'valid' | 'critical' | 'expired' | 'invalid';
  label: string;
}

/**
 * The one verdict the header carries, so it has to mean something.
 *
 * Showing the worst expiry band found on any role would leave it amber for
 * ever: RSTUF gives timestamp a one-day life and renews it on a schedule, so
 * a healthy repository always holds a role inside a day of expiring, and a
 * warning that is always on is not a warning.
 *
 * The narrower question is whether anything is actually wrong. Something
 * expired, or a signature that did not check out, is wrong. Root running down
 * earns a place beside them because root is the one role no worker can renew:
 * it is signed offline, by people, and nothing rescues it automatically.
 *
 * Every other band stays in the table, where a one-day expiry on timestamp
 * reads as the ordinary information it is.
 */
export function verdictFor(overview: OverviewResponse): Verdict {
  const roles = overview.roles ?? [];

  if (overview.status === 'invalid') {
    return { band: 'invalid', label: 'Verification failed' };
  }

  if (
    overview.status === 'expired' ||
    roles.some((role) => role.band === 'expired')
  ) {
    return { band: 'expired', label: 'Expired' };
  }

  const root = roles.find((role) => role.name === 'root');
  if (root && (root.band === 'critical' || root.band === 'expiring')) {
    return { band: 'critical', label: `Root ${root.expires_in}` };
  }

  return { band: 'valid', label: 'All healthy' };
}

/**
 * How old the answer on screen is, in words.
 *
 * A clock time answers a question nobody asked. What sends someone to the
 * refresh button is not knowing whether they are looking at something
 * current, and "checked 4 seconds ago" settles that without a click.
 */
export function ago(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return plural(Math.round(seconds), 'second');

  const minutes = seconds / 60;
  if (minutes < 45) return plural(Math.round(minutes), 'minute');

  return plural(Math.round(minutes / 60), 'hour');
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}
