import { useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import WaveformPlayer from "./WaveformPlayer";
import RegionsPlugin, {
  type Region,
} from "wavesurfer.js/dist/plugins/regions.js";
import { Button } from "./ui/button";
import {
  ticksFromTimes,
  toRelativeTime,
  toAbsoluteTime,
} from "@/lib/regions";
import type { Segment } from "@/types";

interface SegmentWaveformViewProps {
  url: string;
  segment: Segment;
  viewStart: number;
  gridTimes: number[];
  beatTimes: number[];
  onClose: () => void;
  onReady?: (wavesurfer: WaveSurfer) => void;
  onBoundaryChange: (index: number, bounds: { start: number; end: number }) => void;
}

export default function SegmentWaveformView({
  url,
  segment,
  viewStart,
  gridTimes,
  beatTimes,
  onClose,
  onReady,
  onBoundaryChange,
}: SegmentWaveformViewProps) {
  const regionsPlugin = useMemo(() => RegionsPlugin.create(), []);

  const plugins = useMemo(() => [regionsPlugin], [regionsPlugin]);

  const trimRegionRef = useRef<Region | null>(null);
  const isLoopingRef = useRef(false);
  const [isLooping, setIsLooping] = useState(false);

  const handleReady = (ws: WaveSurfer) => {
    ticksFromTimes(gridTimes, viewStart).forEach((tick) => {
      regionsPlugin.addRegion({
        id: tick.id,
        start: tick.start,
        color: "red",
        drag: false,
        resize: true,
      });
    });
    const nonDownbeatBeats = beatTimes.filter((b) => !gridTimes.includes(b));
    ticksFromTimes(nonDownbeatBeats, viewStart).forEach((tick) => {
      regionsPlugin.addRegion({
        id: `beat-${tick.id}`,
        start: tick.start,
        color: "green",
        drag: false,
        resize: true,
      });
    });
    trimRegionRef.current = regionsPlugin.addRegion({
      id: "trim",
      start: toRelativeTime(segment.start, viewStart),
      end: toRelativeTime(segment.end, viewStart),
      drag: false,
      resize: true,
    });
    regionsPlugin.on("region-updated", (region) => {
      if (region.id !== "trim") return;
      onBoundaryChange(segment.index, {
        start: toAbsoluteTime(region.start, viewStart),
        end: toAbsoluteTime(region.end, viewStart),
      });
    });
    regionsPlugin.on("region-out", (region) => {
      if (region.id === "trim" && isLoopingRef.current) region.play(true);
    });
    ws.zoom(300);
    onReady?.(ws);
  };

  const toggleLoop = () => {
    const next = !isLoopingRef.current;
    isLoopingRef.current = next;
    setIsLooping(next);
    if (next) trimRegionRef.current?.play(true);
  };

  return (
    <div className="border-t border-border pt-2 mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">
          {segment.segment_name} — segment view
        </span>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <WaveformPlayer url={url} plugins={plugins} onReady={handleReady} />
      <Button size="sm" onClick={toggleLoop}>
        {isLooping ? "Stop loop" : "Loop segment"}
      </Button>
    </div>
  );
}
