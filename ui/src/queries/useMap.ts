import { apiClient } from "@/api/client";
import type { MusicMap } from "@/types";
import { useQuery } from "@tanstack/react-query";

async function fetchMap(name: string): Promise<MusicMap> {
  const res = await apiClient.GET(`/map/{name}`, {
    params: { path: { name } },
  });
  if (res.error) throw new Error("An error occured");
  return res.data;
}

export function useMap(name: string) {
  return useQuery({
    queryKey: ["map", name],
    queryFn: () => fetchMap(name),
    enabled: !!name,
  });
}
