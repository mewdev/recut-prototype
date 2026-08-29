import type { components } from "@/api/schema";

// Backend shapes — generated from the live OpenAPI schema, don't hand-edit.
export type SourceSummary = components["schemas"]["SourceSummary"];
export type MusicMap = components["schemas"]["MusicMap"];
export type Segment = components["schemas"]["EnrichedSegment"];

// UI-only derived shape, not part of the backend schema.
export interface Section {
  label: string;
  start: number;
  end: number;
}
