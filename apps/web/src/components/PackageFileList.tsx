import { withCacheBust } from "../domain/types";

interface PackageFileListProps {
  readonly files: readonly string[];
  readonly filesBase: string;
  /** Optional: the current run's cache-bust token (see withCacheBust). Download links are
   *  user-initiated fresh requests and don't strictly need this — a click always goes to the
   *  network, never the in-memory fetch cache a stale open tab could be replaying from — but
   *  versioning them too keeps every files_base URL in the app built the same way. */
  readonly runVersion?: number | null;
}

export function PackageFileList({ files, filesBase, runVersion = null }: PackageFileListProps) {
  if (files.length === 0) return null;
  return (
    <div className="package-files">
      <h3 className="package-files__title">Package</h3>
      <ul className="package-files__list">
        {files.map((name) => (
          <li key={name} className="package-files__item">
            <a className="package-files__link" href={withCacheBust(`${filesBase}${name}`, runVersion)} download>
              {name}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
