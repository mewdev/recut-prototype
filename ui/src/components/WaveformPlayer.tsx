import WavesurferPlayer from "@wavesurfer/react";
import type WaveSurfer from "wavesurfer.js";
import type { WaveSurferOptions } from "wavesurfer.js";
import { useState } from "react";
import { Button } from "./ui/button";

interface WaveformPlayerProps {
  url: string;
  height?: number;
  plugins?: WaveSurferOptions["plugins"];
  onReady?: (wavesurfer: WaveSurfer) => void;
  /**
   * Sample rate wavesurfer decodes into (doesn't affect playback — see
   * wavesurfer.js's own doc comment on this option). Defaults to 8000
   * upstream, which is fine for drawing peaks but not for anything reading
   * getDecodedData() as real audio (e.g. cropAudio.ts). 44100 = CD quality.
   */
  sampleRate?: number;
}

export default function WaveformPlayer({
  url,
  height = 80,
  plugins,
  onReady,
  sampleRate = 44100,
}: WaveformPlayerProps) {
  const [wavesurfer, setWavesurfer] = useState<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loadPercent, setLoadPercent] = useState<number>(0);

  const handleReady = (ws: WaveSurfer) => {
    setWavesurfer(ws);
    setIsPlaying(false);
    onReady?.(ws);
  };

  const onPlayPause = () => {
    if (wavesurfer) {
      wavesurfer.playPause();
    }
  };

  return (
    <div className="waveform-player">
      {loadPercent < 100 && <div>Loading track...{String(loadPercent)}%</div>}
      <WavesurferPlayer
        url={url}
        height={height}
        plugins={plugins}
        sampleRate={sampleRate}
        onReady={handleReady}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        normalize
        onLoading={(_wavesurfer, percent) => setLoadPercent(percent)}
      />
      <Button onClick={onPlayPause}>{isPlaying ? "Pause" : "Play"}</Button>
    </div>
  );
}
