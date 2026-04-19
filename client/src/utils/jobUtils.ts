// client/src/lib/jobUtils.ts

const BASE = "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("access_token") ?? "";
  return {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`,
  };
}

export const getAppliedJobs = async (jobSeekerId: number) => {
  const res = await fetch(
    `${BASE}/api/job-seeker/${jobSeekerId}/applied-jobs`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to fetch applied jobs");
  const data = await res.json();
  return { ...data, applications: data.applications ?? [] };
};

export const getSavedJobs = async (seekerId: number) => {
  const res = await fetch(
    `${BASE}/api/job-seeker/${seekerId}/saved-jobs`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to fetch saved jobs");
  const data = await res.json();
  return { ...data, saved_jobs: data.saved_jobs ?? [] };
};

export const saveJob = async (jobId: number) => {
  const res = await fetch(
    `${BASE}/api/jobs/${jobId}/save`,
    { method: "POST", headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to save job");
  return await res.json();
};

export const unsaveJob = async (jobId: number) => {
  const res = await fetch(
    `${BASE}/api/jobs/${jobId}/save`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to unsave job");
  return await res.json();
};

export const applyToJob = async (jobId: number) => {
  const res = await fetch(
    `${BASE}/api/jobs/${jobId}/apply`,
    { method: "POST", headers: authHeaders() }
  );
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? "Failed to apply");
  return data;
};