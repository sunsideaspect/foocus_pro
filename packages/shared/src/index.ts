export type JobType = "photo" | "video";
export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface Character {
  id: string;
  owner_id: string;
  name: string;
  description?: string | null;
  references: string[];
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  owner_id: string;
  job_type: JobType;
  status: JobStatus;
  character_id?: string | null;
  payload: Record<string, unknown>;
  metadata?: Record<string, unknown> | null;
  error_message?: string | null;
  attempts: number;
  result_object_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobResult {
  id: string;
  status: JobStatus;
  metadata?: Record<string, unknown> | null;
  object_key?: string | null;
  presigned_url?: string | null;
}
