"use client";

import type { Job, JobResult } from "@identity-studio/shared";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createCharacter,
  createPhotoJob,
  createVideoJob,
  getJob,
  getJobResult,
  listJobs
} from "@/lib/api";

const terminalStatuses = new Set(["completed", "failed"]);

export default function HomePage() {
  const [characterName, setCharacterName] = useState("Main Character");
  const [characterDescription, setCharacterDescription] = useState("");
  const [characterRefs, setCharacterRefs] = useState("");
  const [characterId, setCharacterId] = useState("");

  const [prompt, setPrompt] = useState("cinematic portrait, natural skin texture, 85mm lens");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [model, setModel] = useState("default");
  const [cfgScale, setCfgScale] = useState(7);
  const [steps, setSteps] = useState(28);
  const [seed, setSeed] = useState<number | "">("");

  const [motionPrompt, setMotionPrompt] = useState("subtle head turn, soft smile");

  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [results, setResults] = useState<Record<string, JobResult>>({});
  const [error, setError] = useState<string | null>(null);

  const refreshJobs = async () => {
    const items = await listJobs();
    setJobs(items);
  };

  const ensureResultLoaded = async (jobId: string) => {
    if (results[jobId]) {
      return;
    }
    const result = await getJobResult(jobId);
    setResults((prev) => ({ ...prev, [jobId]: result }));
  };

  useEffect(() => {
    refreshJobs().catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!activeJob || terminalStatuses.has(activeJob.status)) {
      return;
    }
    const timer = setInterval(async () => {
      try {
        const updated = await getJob(activeJob.id);
        setActiveJob(updated);
        if (updated.status === "completed") {
          await ensureResultLoaded(updated.id);
          await refreshJobs();
        }
      } catch (err) {
        setError((err as Error).message);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [activeJob, results]);

  const latestCompletedPhoto = useMemo(
    () => jobs.find((j) => j.job_type === "photo" && j.status === "completed"),
    [jobs]
  );

  const onCreateCharacter = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const character = await createCharacter({
        name: characterName,
        description: characterDescription,
        references: characterRefs
          .split(",")
          .map((r) => r.trim())
          .filter(Boolean)
      });
      setCharacterId(character.id);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onCreatePhotoJob = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!characterId) {
      setError("Create character first");
      return;
    }
    try {
      const job = await createPhotoJob({
        character_id: characterId,
        prompt,
        negative_prompt: negativePrompt,
        model,
        cfg_scale: cfgScale,
        steps,
        seed: seed === "" ? undefined : Number(seed)
      });
      setActiveJob(job);
      await refreshJobs();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onCreateVideoJob = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!characterId) {
      setError("Create character first");
      return;
    }
    try {
      const job = await createVideoJob({
        character_id: characterId,
        motion_prompt: motionPrompt,
        source_photo_job_id: latestCompletedPhoto?.id
      });
      setActiveJob(job);
      await refreshJobs();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <main>
      <h1>Identity Studio MVP</h1>
      {error ? <div className="card">Error: {error}</div> : null}

      <section className="card">
        <h2>1) Character Profile</h2>
        <form onSubmit={onCreateCharacter}>
          <label>
            Name
            <input value={characterName} onChange={(e) => setCharacterName(e.target.value)} />
          </label>
          <label>
            Description
            <textarea
              value={characterDescription}
              onChange={(e) => setCharacterDescription(e.target.value)}
            />
          </label>
          <label>
            Reference URLs (comma separated)
            <input value={characterRefs} onChange={(e) => setCharacterRefs(e.target.value)} />
          </label>
          <button type="submit">Create Character</button>
        </form>
        <div>character_id: {characterId || "-"}</div>
      </section>

      <section className="card">
        <h2>2) Photo Job</h2>
        <form onSubmit={onCreatePhotoJob}>
          <label>
            Prompt
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          </label>
          <label>
            Negative Prompt
            <textarea value={negativePrompt} onChange={(e) => setNegativePrompt(e.target.value)} />
          </label>
          <div className="inline">
            <label>
              Model
              <input value={model} onChange={(e) => setModel(e.target.value)} />
            </label>
            <label>
              CFG
              <input
                type="number"
                step="0.1"
                value={cfgScale}
                onChange={(e) => setCfgScale(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="inline">
            <label>
              Steps
              <input
                type="number"
                value={steps}
                onChange={(e) => setSteps(Number(e.target.value))}
              />
            </label>
            <label>
              Seed (optional)
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value === "" ? "" : Number(e.target.value))}
              />
            </label>
          </div>
          <button type="submit">Create Photo Job</button>
        </form>
      </section>

      <section className="card">
        <h2>3) Video Job (stub pipeline)</h2>
        <form onSubmit={onCreateVideoJob}>
          <label>
            Motion prompt
            <input value={motionPrompt} onChange={(e) => setMotionPrompt(e.target.value)} />
          </label>
          <button type="submit">Create Video Job</button>
        </form>
      </section>

      <section className="card">
        <h2>Status Polling</h2>
        {activeJob ? (
          <div>
            <div>job_id: {activeJob.id}</div>
            <div>
              status: <span className="status-pill">{activeJob.status}</span>
            </div>
            <div>attempts: {activeJob.attempts}</div>
          </div>
        ) : (
          <div>No active job yet.</div>
        )}
      </section>

      <section className="card">
        <h2>Gallery & History</h2>
        <button
          type="button"
          onClick={async () => {
            setError(null);
            try {
              await refreshJobs();
              const completed = jobs.filter((job) => job.status === "completed");
              await Promise.all(completed.map((job) => ensureResultLoaded(job.id)));
            } catch (err) {
              setError((err as Error).message);
            }
          }}
        >
          Refresh Gallery
        </button>
        {jobs.length === 0 ? <div>No jobs.</div> : null}
        {jobs.map((job) => {
          const result = results[job.id];
          return (
            <div key={job.id} className="card">
              <div>
                <strong>{job.job_type}</strong> / {job.id}
              </div>
              <div>status: {job.status}</div>
              <div>created: {new Date(job.created_at).toLocaleString()}</div>
              {job.status === "completed" && job.job_type === "photo" && result?.presigned_url ? (
                <img className="preview" src={result.presigned_url} alt={job.id} />
              ) : null}
              {job.metadata ? (
                <pre>{JSON.stringify(job.metadata, null, 2)}</pre>
              ) : (
                <div>No metadata yet.</div>
              )}
            </div>
          );
        })}
      </section>
    </main>
  );
}
