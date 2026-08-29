import createClient from "openapi-fetch";
import type { paths } from "./schema";

// baseUrl empty — same-origin, Vite's dev proxy (vite.config.ts) forwards
// /sources, /map, /audio to the Flask server on :5050.
export const apiClient = createClient<paths>({ baseUrl: "" });
