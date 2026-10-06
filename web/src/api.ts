export type Info = {
  model_id: string;
  is_free: boolean;
  render_available: boolean;
  render_missing: string | null;
};

export type ReviewItem = {
  line: number;
  source: string;
  kind: string;
  target: string;
  confidence: number;
  evidence: string | null;
};

export type Review = {
  threshold: number;
  items: ReviewItem[];
};

export type RegenerateResult = {
  puml: string;
  svg: string | null;
  render_error: string | null;
  review_md: string;
  review: Review;
  warnings: string[];
  model_id: string;
  cost_usd: number;
  latency_seconds: number;
  class_count: number;
  relationship_count: number;
};

const UNREACHABLE = "Could not reach the uml-regen server.";

async function failure(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as { message?: string };
    return new Error(body.message ?? `Request failed (${res.status}).`);
  } catch {
    return new Error(`Request failed (${res.status}).`);
  }
}

async function send(url: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error(UNREACHABLE);
  }
  if (!res.ok) throw await failure(res);
  return res;
}

export async function getInfo(): Promise<Info> {
  return (await send("/api/info")).json();
}

export async function regenerate(image: File): Promise<RegenerateResult> {
  const form = new FormData();
  form.append("image", image);
  return (await send("/api/regenerate", { method: "POST", body: form })).json();
}

export async function renderPuml(puml: string): Promise<string> {
  const res = await send("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ puml }),
  });
  return ((await res.json()) as { svg: string }).svg;
}
