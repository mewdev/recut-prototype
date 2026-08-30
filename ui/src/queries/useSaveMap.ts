import { apiClient } from "@/api/client";
import type { MusicMap } from "@/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

interface SegmentBoundaryUpdate {
  index: number;
  start: number;
  end: number;
}

async function saveMap(
  name: string,
  segments: SegmentBoundaryUpdate[],
): Promise<MusicMap> {
  const res = await apiClient.PATCH("/map/{name}", {
    params: { path: { name } },
    body: { segments },
  });
  if (res.error) throw new Error("An error occured");
  return res.data;
}

export function useSaveMap(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (segments: SegmentBoundaryUpdate[]) => saveMap(name, segments),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["map", name] });
    },
  });
}
