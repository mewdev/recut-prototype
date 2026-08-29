import SourceList from "@/components/SourceList";
import SourceWaveformView from "@/components/SourceWaveformView";
import { useSources } from "@/queries/useSources";
import { useMap } from "@/queries/useMap";
import { useSearch, useNavigate } from "@tanstack/react-router";
// import type { Section } from "@/types";

// const PX_PER_SEC = 6;

export default function MapEditorPage() {
  const { source } = useSearch({ from: "/editor" });
  const navigate = useNavigate({ from: "/editor" });

  const sourcesQuery = useSources();
  const mapQuery = useMap(source ?? "");

  // const [boundaries, setBoundaries] = useState<number[]>([]);

  // TODO(human) — Step 1: wire real data with TanStack Query + the typed
  // apiClient (src/api/client.ts, generated from the backend's OpenAPI
  // schema via `npm run gen:api`).
  //
  // Design this however you think best practice — a couple of things worth
  // knowing going in, not prescribing the shape:
  //
  // - `apiClient.GET("/sources")` (and "/map/{name}") return a promise
  //   resolving to `{ data, error, response }` — they do NOT throw on a
  //   non-2xx response the way `fetch` alone doesn't either. TanStack
  //   Query's `queryFn` expects a promise that resolves to the data or
  //   *throws* on failure — you'll need to bridge that gap yourself (throw
  //   when `error` is present, return `data` otherwise).
  // - `activeSourceName` needs to start `null` (nothing loaded yet) and get
  //   defaulted to the first `"ready"` source once the sources query
  //   resolves, but a user click on SourceList should still be able to
  //   override it afterward. Worth thinking about where the query for
  //   `/map/{name}` gets `enabled: false`'d until a source is actually
  //   selected.
  // - `boundaries` (this component's own local drag state) still needs
  //   initializing from the fetched map once it loads — every segment's
  //   `end` except the last (`map.segments.slice(0, -1).map(s => s.end)`),
  //   the interior join points. That's local UI state, not query state —
  //   don't try to force it into a `useQuery` itself.
  //
  // Common pattern worth researching: small custom hooks per endpoint
  // (e.g. a `useSources()`, `useMap(name)`) that wrap `useQuery` — keeps the
  // query key + queryFn pairing in one place instead of inlined here.
  //
  // The JSX below references `map` (MusicMap | null, from @/types) —
  // nothing declares it yet, that's this TODO. `<SourceList />` currently
  // takes no props (it's its own TODO now, might own its own /sources
  // fetch) — how the user's click there gets back up to set
  // `activeSourceName` here is an open design question, yours to resolve
  // (a callback prop you add to SourceList, lifting the sources query up
  // to this component instead, context — pick what makes sense once you've
  // written SourceList and see what it actually needs).

  // function handleBoundaryChange(index: number, newTime: number) {
  //   setBoundaries((b) => b.map((v, i) => (i === index ? newTime : v)));
  // }

  // if (!map || !activeSourceName) {
  //   return <div className="p-4 text-sm text-muted-foreground">Loading…</div>;
  // }

  // const bounds = [0, ...boundaries, map.duration];
  // const sections: Section[] = map.segments.map((seg, i) => ({
  //   label: seg.segment_name,
  //   start: bounds[i],
  //   end: bounds[i + 1],
  // }));

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
