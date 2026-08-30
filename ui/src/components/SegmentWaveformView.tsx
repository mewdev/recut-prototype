import { useMemo } from "react";
import type WaveSurfer from "wavesurfer.js";
import WaveformPlayer from "./WaveformPlayer";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import { Button } from "./ui/button";
import type { Segment } from "@/types";

interface SegmentWaveformViewProps {
  url: string;
  segment: Segment;
  onClose: () => void;
  onReady?: (wavesurfer: WaveSurfer) => void;
}

export default function SegmentWaveformView({
  url,
  segment,
  onClose,
  onReady,
}: SegmentWaveformViewProps) {
  const regionsPlugin = useMemo(() => RegionsPlugin.create(), []);

  const plugins = useMemo(() => [regionsPlugin], [regionsPlugin]);

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
      <WaveformPlayer url={url} plugins={plugins} onReady={onReady} />
    </div>
  );
}
