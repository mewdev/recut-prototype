function encodeWav(
  channelData: Float32Array[],
  frameCount: number,
  numChannels: number,
  sampleRate: number,
): Blob {
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = frameCount * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++)
      view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < frameCount; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = Math.max(-1, Math.min(1, channelData[ch][i]));
      view.setInt16(
        offset,
        sample < 0 ? sample * 0x8000 : sample * 0x7fff,
        true,
      );
      offset += 2;
    }
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export function cropToWavBlob(
  buffer: AudioBuffer,
  start: number,
  end: number,
): Blob {
  const sampleRate = buffer.sampleRate;
  const startSample = Math.max(0, Math.floor(start * sampleRate));
  const endSample = Math.min(buffer.length, Math.ceil(end * sampleRate));
  const frameCount = Math.max(0, endSample - startSample);
  const numChannels = buffer.numberOfChannels;

  const channelData: Float32Array[] = [];
  for (let ch = 0; ch < numChannels; ch++) {
    channelData.push(
      buffer.getChannelData(ch).subarray(startSample, endSample),
    );
  }

  return encodeWav(channelData, frameCount, numChannels, sampleRate);
}
