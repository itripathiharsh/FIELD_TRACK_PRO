/**
 * True when an error is a failed dynamic import (a code-split chunk that could not
 * be fetched: offline, or a new deploy replaced the old hashed file names).
 */
export function isChunkLoadError(error: unknown): boolean {
  if (!error) return false;
  const name = (error as { name?: unknown }).name;
  const message = String((error as { message?: unknown }).message ?? error);
  return (
    name === 'ChunkLoadError' ||
    /Failed to fetch dynamically imported module/i.test(message) ||
    /error loading dynamically imported module/i.test(message) ||
    /Importing a module script failed/i.test(message) ||
    /Loading chunk [\w-]+ failed/i.test(message) ||
    /Unable to preload CSS/i.test(message)
  );
}
