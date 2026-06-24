// frontend/src/features/schema-explorer/components/NullPercentageBar.tsx

interface NullPercentageBarProps {
  nullPercentage: number; // 0.0–1.0
}

export function NullPercentageBar({ nullPercentage }: NullPercentageBarProps) {
  const pct = Math.round(nullPercentage * 100);
  const barColor =
    nullPercentage <= 0.1
      ? "bg-green-500"
      : nullPercentage <= 0.5
        ? "bg-amber-500"
        : "bg-red-500";

  if (pct === 0) return null;

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <div className="w-12 h-1 rounded-full bg-muted overflow-hidden shrink-0">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground shrink-0">{pct}% null</span>
    </div>
  );
}