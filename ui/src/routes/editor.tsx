import { createFileRoute } from "@tanstack/react-router";
import MapEditorPage from "@/pages/MapEditorPage";
import z from "zod";

export const Route = createFileRoute("/editor")({
  component: MapEditorPage,
  validateSearch: (search: Record<string, unknown>) =>
    z.object({ source: z.string().optional() }).parse(search),
});
