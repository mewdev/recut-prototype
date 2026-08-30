import { useEffect, useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import WaveformPlayer from "./WaveformPlayer";
import SegmentWaveformView from "./SegmentWaveformView";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import { randomColor, regionsFromSegments } from "@/lib/regions";
import { cropToWavBlob } from "@/lib/cropAudio";
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

  const mainWavesurferRef = useRef<WaveSurfer | null>(null);
  const segmentWavesurferRef = useRef<WaveSurfer | null>(null);

  useEffect(() => {
    return () => {
      if (openSegmentUrl) URL.revokeObjectURL(openSegmentUrl);
    };
  }, [openSegmentUrl]);

  const regions = regionsFromSegments(musicMap);

  const segmentSelect = (segment: Segment) => {
    const buffer = mainWavesurferRef.current?.getDecodedData();
    if (!buffer) return;
    const blob = cropToWavBlob(buffer, segment.start, segment.end);
    setOpenSegment(segment);
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
      {openSegment && openSegmentUrl && (
        <SegmentWaveformView
          url={openSegmentUrl}
          segment={openSegment}
          onClose={() => setOpenSegment(null)}
          onReady={handleSegmentReady}
          key={openSegment.index}
        />
      )}
    </div>
  );
}
