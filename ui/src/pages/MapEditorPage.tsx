import SourceList from "@/components/SourceList";
import SourceWaveformView from "@/components/SourceWaveformView";
import { useSources } from "@/queries/useSources";
import { useMap } from "@/queries/useMap";
import { useSearch, useNavigate } from "@tanstack/react-router";

export default function MapEditorPage() {
  const { source } = useSearch({ from: "/editor" });
  const navigate = useNavigate({ from: "/editor" });

  const sourcesQuery = useSources();
  const mapQuery = useMap(source ?? "");

  return (
    <div className="flex w-full h-screen bg-background text-sm">
      <div className="w-52 border-r border-border flex flex-col shrink-0">
        <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Sources
        </div>
        <SourceList
          sources={sourcesQuery.data}
          isLoading={sourcesQuery.isLoading}
          isError={sourcesQuery.isError}
          error={sourcesQuery.error}
          onSelect={(name) =>
            navigate({ search: (prev) => ({ ...prev, source: name }) })
          }
        />

        <div className="px-3 py-2 mt-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Structure
        </div>
        {/* TODO: create an interactive graph of each segment (beats, bars) which after click moves the main player playhead ot the relevant position */}
        {/* <div className="flex-1 overflow-y-auto px-2">
          <SectionList sections={sections} />
        </div> */}
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="text-xs text-muted-foreground mb-2">
          {source ? (
            <span>{source} — drag boundaries to adjust</span>
          ) : (
            <span>Select the track on the left to adjust the boundaries</span>
          )}
        </div>
        {source && mapQuery.data && (
          <div className="overflow-x-auto pb-2">
            <SourceWaveformView
              sourceName={source ?? ""}
              musicMap={mapQuery.data}
            />
          </div>
        )}
      </div>
    </div>
  );
}
