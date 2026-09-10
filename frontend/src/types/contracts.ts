export type DiscussionStatus = "DRAFT" | "CAST_READY" | "RUNNING" | "FINISHED" | "FAILED";
export type ParticipantRole = "moderator" | "expert";
export type RuntimeStatus = "idle" | "preparing" | "speaking";
export type InsightType = "consensus" | "disagreement";
export type SummaryStatus = "pending" | "succeeded" | "fallback";

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
  cast_confirmed_at: string | null;
  summary: string | null;
  summary_status: SummaryStatus;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  participants: ParticipantDto[];
  utterances: UtteranceDto[];
  insights: InsightDto[];
}

export interface UtteranceDto {
  id: string;
  discussion_id: string;
  participant_id: string;
  sequence: number;
  content: string;
  created_at: string;
}

export interface InsightDto {
  id: string;
  discussion_id: string;
  type: InsightType;
  content: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DiscussionListItemDto {
  id: string;
  topic: string;
  expert_count: number;
  status: DiscussionStatus;
  participant_count: number;
  updated_at: string;
}

export interface DiscussionListResponse {
  items: DiscussionListItemDto[];
}

export interface ConfirmationDto {
  id: string;
  status: DiscussionStatus;
  cast_confirmed: boolean;
  cast_confirmed_at: string | null;
  studio_path: string;
}

export interface StartDiscussionDto {
  id: string;
  status: DiscussionStatus;
  started_at: string | null;
}

export interface StopDiscussionDto {
  id: string;
  status: DiscussionStatus;
  stop_requested: boolean;
}

export interface RetrySummaryDto {
  id: string;
  status: DiscussionStatus;
  summary_status: SummaryStatus;
  retry_requested: boolean;
}

export interface DiscussionSnapshotEvent {
  discussion_id: string;
  discussion: DiscussionDto;
}

export interface ParticipantStatusChangedEvent {
  discussion_id: string;
  participant: Pick<ParticipantDto, "id" | "runtime_status" | "public_focus">;
}

export interface UtteranceCreatedEvent {
  discussion_id: string;
  utterance: UtteranceDto;
}

export interface InsightsUpdatedEvent {
  discussion_id: string;
  insights: InsightDto[];
}

export interface DiscussionFinishedEvent {
  discussion_id: string;
  status: "FINISHED";
  summary: string | null;
  summary_status: SummaryStatus;
  finished_at: string | null;
}

export interface DiscussionErrorEvent {
  discussion_id: string;
  final_status: "FAILED";
  error: ErrorResponse["error"];
}
