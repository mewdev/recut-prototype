import { useMemo } from "react";
import WaveformPlayer from "./WaveformPlayer";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import { randomColor, regionsFromSegments } from "@/lib/regions";
import type { MusicMap } from "@/types";

interface SourceWaveformViewProps {
  sourceName: string;
  musicMap: MusicMap;
}

// TODO: implement regions overlap, save, adding new segments,...

export default function SourceWaveformView({
  sourceName,
  musicMap,
}: SourceWaveformViewProps) {
  const regionsPlugin = useMemo(() => RegionsPlugin.create(), []);
  const plugins = useMemo(() => [regionsPlugin], [regionsPlugin]);

  const regions = regionsFromSegments(musicMap);

  const regionsConfig = (regionsPlugin: RegionsPlugin) => {
    regions.forEach((region) => {
      regionsPlugin.addRegion({
        start: region.start,
        end: region.end,
        content: region.content,
        color: randomColor(),
      });
    });
    regionsPlugin.on("region-clicked", (region, e) => {
      e.stopPropagation();
      region.play(true);
    });
  };

  return (
    <WaveformPlayer
      url={`/audio/${sourceName}`}
      plugins={plugins}
      onReady={() => regionsConfig(regionsPlugin)}
    />
  );
}
