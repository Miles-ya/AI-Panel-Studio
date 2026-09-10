import type {
  ConfirmationDto,
  DiscussionDto,
  DiscussionListResponse,
  ErrorResponse,
  RetrySummaryDto,
  StartDiscussionDto,
  StopDiscussionDto,
} from "@/types/contracts";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ErrorResponse | null;
    throw new ApiError(response.status, body?.error.code ?? "REQUEST_FAILED", body?.error.message ?? "请求失败，请稍后重试。");
  }
  return response.json() as Promise<T>;
}

export const api = {
  listDiscussions: (signal?: AbortSignal) => request<DiscussionListResponse>("/api/discussions", { signal }),
  getDiscussion: (id: string, signal?: AbortSignal) => request<DiscussionDto>(`/api/discussions/${id}`, { signal }),
  createDiscussion: (topic: string, expertCount: number) => request<DiscussionDto>("/api/discussions", { method: "POST", body: JSON.stringify({ topic, expert_count: expertCount }) }),
  generateCast: (id: string) => request<DiscussionDto>(`/api/discussions/${id}/generate-cast`, { method: "POST" }),
  confirmDiscussion: (id: string) => request<ConfirmationDto>(`/api/discussions/${id}/confirm`, { method: "POST", body: "{}" }),
  startDiscussion: (id: string) => request<StartDiscussionDto>(`/api/discussions/${id}/start`, { method: "POST", body: "{}" }),
  stopDiscussion: (id: string) => request<StopDiscussionDto>(`/api/discussions/${id}/stop`, { method: "POST", body: "{}" }),
  retrySummary: (id: string) => request<RetrySummaryDto>(`/api/discussions/${id}/retry-summary`, { method: "POST", body: "{}" }),
};

export function eventUrl(discussionId: string): string {
  return `${apiBaseUrl}/api/discussions/${discussionId}/events`;
}
