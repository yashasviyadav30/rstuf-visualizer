import type { BinSummary } from '../../../api/types';

interface Props {
  bins: BinSummary[];
  total: number;
  loading: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
}

export function BinList({ bins, total, loading, selected, onSelect }: Props) {
  if (loading) return <p className="muted">Counting…</p>;
  if (bins.length === 0) {
    return <p className="muted">This repository delegates to no roles.</p>;
  }

  return (
    <>
      <p className="muted">
        {total} artifact{total === 1 ? '' : 's'} across {bins.length} role
        {bins.length === 1 ? '' : 's'}
      </p>
      <ul className="bins">
        {bins.map((bin) => (
          <li key={bin.name}>
            <button
              className={`bin${bin.name === selected ? ' is-selected' : ''}`}
              type="button"
              onClick={() => onSelect(bin.name)}
              disabled={!bin.available}
            >
              <span className="bin__name">{bin.name}</span>
              {/* A bin holding nothing keeps its place with a count of zero.
                  Its absence would say something different: that it does not
                  exist. An unreadable one says so instead of showing 0, which
                  would be a claim nobody checked. */}
              <span className="bin__count">
                {bin.available ? bin.count : 'unreadable'}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
