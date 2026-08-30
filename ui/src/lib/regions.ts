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
