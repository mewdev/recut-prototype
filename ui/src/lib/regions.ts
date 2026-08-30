import type { MusicMap, Segment } from "@/types";

const random = (min: number, max: number) => Math.random() * (max - min) + min;

export const randomColor = () =>
  `rgba(${random(0, 255)}, ${random(0, 255)}, ${random(0, 255)}, 0.25)`;

export const regionsFromSegments = (musicMap: MusicMap) =>
  musicMap.segments.map((segment: Segment) => {
    return {
      id: String(segment.index),
      start: segment.start,
      end: segment.end,
      content: segment.segment_name,
    };
  });

// segment.downbeats are absolute track time (see helpers.py:downbeats_in) — every
// time we place them on a segment-relative waveform (the cropped preview) or write a
// dragged position back to the map, we have to convert across that boundary explicitly.
export const toAbsoluteTime = (relative: number, segmentStart: number) =>
  relative + segmentStart;

export const toRelativeTime = (absolute: number, segmentStart: number) =>
  absolute - segmentStart;

export const ticksFromTimes = (times: number[], originStart: number) =>
  times.map((time, i) => {
    const t = toRelativeTime(time, originStart);
    return { id: `bar-${i}`, start: t, end: t };
  });

export const barTicksFromSegment = (segment: Segment) =>
  ticksFromTimes(segment.downbeats, segment.start);

export const snapToGrid = (time: number, grid: number[]): number => {
  if (!grid || grid.length === 0) {
    throw new Error(`snapToGrid: grid must be non-empty, got: ${grid}`);
  }
  const indexFound = grid.findIndex((g) => g >= time);

  if (indexFound === -1) return grid[grid.length - 1];
  if (indexFound === 0) return grid[0];

  const distBefore = Math.abs(grid[indexFound - 1] - time);
  const distAfter = Math.abs(grid[indexFound] - time);
  return distBefore < distAfter ? grid[indexFound - 1] : grid[indexFound];
};
