import type { Character, Job, JobResult } from "@identity-studio/shared";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DEV_USER = "dev-user";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Dev-User": DEV_USER,
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}

export interface CreateCharacterInput {
  name: string;
  description?: string;
  references: string[];
}

export interface CreatePhotoJobInput {
  character_id: string;
  prompt: string;
  negative_prompt?: string;
  model?: string;
  cfg_scale?: number;
  steps?: number;
  seed?: number;
  width?: number;
  height?: number;
  idempotency_key?: string;
}

export async function createCharacter(input: CreateCharacterInput): Promise<Character> {
  return request<Character>("/characters", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createPhotoJob(input: CreatePhotoJobInput): Promise<Job> {
  return request<Job>("/jobs/photo", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createVideoJob(input: {
  character_id: string;
  motion_prompt: string;
  source_photo_job_id?: string;
  fps?: number;
  seconds?: number;
  idempotency_key?: string;
}): Promise<Job> {
  return request<Job>("/jobs/video", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`);
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  return request<JobResult>(`/jobs/${jobId}/result`);
}

export async function listJobs(): Promise<Job[]> {
  return request<Job[]>("/jobs?limit=100");
}
