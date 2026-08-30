import { useEffect, useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import WaveformPlayer from "./WaveformPlayer";
import SegmentWaveformView from "./SegmentWaveformView";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import { randomColor, regionsFromSegments } from "@/lib/regions";
import { cropToWavBlob } from "@/lib/cropAudio";
import { useSaveMap } from "@/queries/useSaveMap";
import { Button } from "./ui/button";
import type { MusicMap, Segment } from "@/types";

interface SourceWaveformViewProps {
  sourceName: string;
  musicMap: MusicMap;
}

export default function SourceWaveformView({
  sourceName,
  musicMap,
}: SourceWaveformViewProps) {
  const regionsPlugin = useMemo(() => RegionsPlugin.create(), []);

  const plugins = useMemo(() => [regionsPlugin], [regionsPlugin]);

  const [openSegment, setOpenSegment] = useState<Segment | null>(null);
  const [openSegmentUrl, setOpenSegmentUrl] = useState<string | null>(null);
  const [openSegmentView, setOpenSegmentView] = useState<{
    viewStart: number;
    gridTimes: number[];
    beatTimes: number[];
  } | null>(null);

  const mainWavesurferRef = useRef<WaveSurfer | null>(null);
  const segmentWavesurferRef = useRef<WaveSurfer | null>(null);

  const [editedSegments, setEditedSegments] = useState<
    Record<number, { start: number; end: number }>
  >({});
  const saveMap = useSaveMap(sourceName);

  const handleBoundaryChange = (
    index: number,
    bounds: { start: number; end: number },
  ) => {
    setEditedSegments((prev) => ({ ...prev, [index]: bounds }));
  };

  const handleSave = () => {
    const segments = Object.entries(editedSegments).map(([index, bounds]) => ({
      index: Number(index),
      ...bounds,
    }));
    saveMap.mutate(segments, {
      onSuccess: () => setEditedSegments({}),
    });
  };

  useEffect(() => {
    return () => {
      if (openSegmentUrl) URL.revokeObjectURL(openSegmentUrl);
    };
  }, [openSegmentUrl]);

  const regions = regionsFromSegments(musicMap);

  const segmentSelect = (segment: Segment) => {
    const buffer = mainWavesurferRef.current?.getDecodedData();
    if (!buffer) return;

    const idx = musicMap.segments.findIndex((s) => s.index === segment.index);
    const prev = musicMap.segments[idx - 1];
    const next = musicMap.segments[idx + 1];
    const prevDownbeat = prev?.downbeats[prev.downbeats.length - 1];
    const nextDownbeat = next?.downbeats[0];

    const viewStart = prevDownbeat ?? segment.start;
    const viewEnd = nextDownbeat ?? segment.end;
    const gridTimes = [
      ...(prevDownbeat !== undefined ? [prevDownbeat] : []),
      ...segment.downbeats,
      ...(nextDownbeat !== undefined ? [nextDownbeat] : []),
    ];
    const beatTimes = musicMap.beats.filter(
      (b) => b >= viewStart && b <= viewEnd,
    );

    const blob = cropToWavBlob(buffer, viewStart, viewEnd);
    setOpenSegment(segment);
    setOpenSegmentView({ viewStart, gridTimes, beatTimes });
    setOpenSegmentUrl(URL.createObjectURL(blob));
  };

  const regionsConfig = (regionsPlugin: RegionsPlugin) => {
    regions.forEach((region) => {
      regionsPlugin.addRegion({
        id: region.id,
        start: region.start,
        end: region.end,
        content: region.content,
        color: randomColor(),
      });
    });
    regionsPlugin.on("region-clicked", (region, e) => {
      e.stopPropagation();
      const segment = musicMap.segments.find(
        (s) => String(s.index) === region.id,
      );
      if (segment) segmentSelect(segment);
    });
  };

  const handleMainReady = (ws: WaveSurfer) => {
    mainWavesurferRef.current = ws;
    ws.on("play", () => segmentWavesurferRef.current?.pause());
    regionsConfig(regionsPlugin);
  };

  const handleSegmentReady = (ws: WaveSurfer) => {
    segmentWavesurferRef.current = ws;
    ws.on("play", () => mainWavesurferRef.current?.pause());
  };

  return (
    <div>
      <WaveformPlayer
        url={`/audio/${sourceName}`}
        plugins={plugins}
        onReady={handleMainReady}
      />
      {openSegment && openSegmentUrl && openSegmentView && (
        <SegmentWaveformView
          url={openSegmentUrl}
          segment={openSegment}
          viewStart={openSegmentView.viewStart}
          gridTimes={openSegmentView.gridTimes}
          beatTimes={openSegmentView.beatTimes}
          onClose={() => setOpenSegment(null)}
          onReady={handleSegmentReady}
          onBoundaryChange={handleBoundaryChange}
          key={openSegment.index}
        />
      )}
      {Object.keys(editedSegments).length > 0 && (
        <div className="flex items-center gap-2 mt-2">
          <span className="text-xs text-muted-foreground">
            Unsaved boundary changes ({Object.keys(editedSegments).length})
          </span>
          <Button size="sm" onClick={handleSave} disabled={saveMap.isPending}>
            {saveMap.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      )}
    </div>
  );
}
