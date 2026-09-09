export type DiscussionStatus = "DRAFT" | "CAST_READY" | "RUNNING" | "FINISHED" | "FAILED";
export type ParticipantRole = "moderator" | "expert";
export type RuntimeStatus = "idle" | "preparing" | "speaking";
export type InsightType = "consensus" | "disagreement";

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface ParticipantDto {
  id: string;
  discussion_id: string;
  role: ParticipantRole;
  name: string;
  profession: string;
  title: string;
  stance: string;
  color: string;
  runtime_status: RuntimeStatus;
  public_focus: string | null;
}

export interface DiscussionDto {
  id: string;
  topic: string;
  expert_count: number;
  max_public_utterances: number;
  status: DiscussionStatus;
  cast_confirmed: boolean;
}
