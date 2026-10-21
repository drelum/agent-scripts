export function chooseWindow<T extends { id: string; start: number; end: number }>(
  windows: T[],
  timestamp: number,
  selected?: string,
): T | undefined {
  return windows.find(
    (w) => (!selected || w.id === selected) && timestamp >= w.start && timestamp <= w.end,
  );
}
