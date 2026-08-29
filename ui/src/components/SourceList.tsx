import { FileAudio } from "lucide-react";
import type { SourceSummary } from "@/types";

type SourceListProps = {
  sources: SourceSummary[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onSelect: (name: string) => void;
};

export default function SourceList({
  sources,
  isLoading,
  isError,
  error,
  onSelect,
}: SourceListProps) {
  if (isLoading)
    return (
      <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>
    );
  if (isError)
    return (
      <div className="px-3 py-2 text-xs text-destructive">{error?.message}</div>
    );

  return (
    <div className="px-2 space-y-0.5">
      {sources?.map((item) => (
        <div
          key={item.name}
          onClick={
            item.status === "ready" ? () => onSelect(item.name) : undefined
          }
          className={`flex items-center gap-2 px-2 py-1.5 rounded-md ${
            item.status === "ready"
              ? "cursor-pointer hover:bg-muted"
              : "cursor-not-allowed opacity-50"
          }`}
        >
          <FileAudio className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="truncate text-xs">{item.name}</span>
          {item.status !== "ready" && (
            <span className="ml-auto text-xs text-muted-foreground shrink-0">
              {item.status}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
