import { apiClient } from "@/api/client";
import type { SourceSummary } from "@/types";
import { useQuery } from "@tanstack/react-query";


async function fetchSources(): Promise<SourceSummary[]>{
    const res = await apiClient.GET("/sources")
    if (res.error)
        throw new Error("An error occured")
    return res.data
}

export function useSources(){
    return useQuery({
        queryKey: ["sources"], queryFn: fetchSources
    })
}