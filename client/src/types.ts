export type Spec = {
  idea: string;
  kind: "clip" | "drama" | "film" | "series";
  orientation: "portrait" | "landscape" | "square";
  target_seconds: number;
  episodes: number;
  backend: "demo" | "local";
  prewrite_season?: boolean;
  language: "English";
  style: string;
  idempotency_key: string;
};
export type Character = {
  id: string;
  name: string;
  appearance: string;
  goal: string;
  voice: string;
};
export type Place = { id: string; name: string; description: string };
export type Outline = {
  number: number;
  title: string;
  summary: string;
  outcome: string;
};
export type Shot = {
  id: string;
  number: number;
  duration: number;
  camera: string;
  action: string;
  narration: string;
  speaker_id: string;
  character_ids: string[];
  location_id: string;
};
export type Episode = {
  id: string;
  number: number;
  outline: Outline;
  status: string;
  script: { number: number; screenplay: string; shots: Shot[] } | null;
};
export type Asset = {
  id: string;
  role: string;
  sha256: string;
  metadata: {
    episode: number;
    entity_id?: string;
    shot_id?: string;
    is_mock: boolean;
    provider: string;
    width?: number;
    height?: number;
    duration?: number;
    dialogue_present?: boolean;
  };
};
export type Step = {
  id: string;
  stage: string;
  state: string;
  attempts: number;
  error: string | null;
};
export type Job = {
  id: string;
  episode: number;
  state: string;
  error: string | null;
  steps: Step[];
};
export type Project = {
  id: string;
  title: string;
  spec: Spec;
  status: string;
  revision: number;
  plan: {
    title: string;
    logline: string;
    ending: string;
    world_rules: string[];
    characters: Character[];
    locations: Place[];
    episodes: Outline[];
  } | null;
  episodes: Episode[];
  jobs: Job[];
  assets: Asset[];
  canon: {
    entity_id: string;
    episode: number;
    field: string;
    value: string;
    reason: string;
  }[];
};
export type Recent = Pick<Project, "id" | "title" | "spec" | "status"> & {
  created: number;
};
export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${url}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ message: "Studio could not be reached." }));
    throw new Error(
      data.message +
        (data.details
          ? ` ${data.details.map((d: { message: string }) => d.message).join(" ")}`
          : ""),
    );
  }
  return response.json();
}
export const assetUrl = (asset: Asset, download = false) =>
  `/api/assets/${asset.id}/content${download ? "?download=true" : ""}`;
export const stageLabel = (stage: string) =>
  ({
    PLAN: "Preparing your story",
    SCRIPT: "Writing the screenplay",
    DRAFT: "Prewriting the season",
    REFERENCE: "Creating references",
    FRAME: "Composing keyframes",
    CLIP: "Animating shots",
    AUDIO: "Building soundtrack",
    EXPORT: "Finishing movie",
    COMPLETED: "Ready to watch",
    QUEUED: "Waiting to begin",
    FAILED: "Needs attention",
    PAUSED: "Paused",
    CANCELLED: "Cancelled",
  })[stage] || stage;
