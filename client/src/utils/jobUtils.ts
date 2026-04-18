<<<<<<< HEAD
export const getAppliedJobs = async (jobSeekerId: number) => {
  const res = await fetch(`http://localhost:8000/api/job-seeker/${jobSeekerId}/applied-jobs`);
=======
import { API_BASE } from '../config';

export const getAppliedJobs = async (jobSeekerId: number) => {
  const res = await fetch(`${API_BASE}/api/job-seeker/${jobSeekerId}/applied-jobs`);
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
  if (!res.ok) throw new Error("Failed to fetch applied jobs");
  return await res.json();
};





export const saveJob = async (seekerId: number, jobId: number) => {
<<<<<<< HEAD
  const res = await fetch(`http://localhost:8000/api/job-seeker/${seekerId}/save/${jobId}`, {
=======
  const res = await fetch(`${API_BASE}/api/job-seeker/${seekerId}/save/${jobId}`, {
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
    method: 'POST',
  });
  if (!res.ok) throw new Error("Failed to save job");
  return await res.json();
};

export const getSavedJobs = async (seekerId: number) => {
<<<<<<< HEAD
  const res = await fetch(`http://localhost:8000/api/job-seeker/${seekerId}/saved-jobs`);
=======
  const res = await fetch(`${API_BASE}/api/job-seeker/${seekerId}/saved-jobs`);
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
  if (!res.ok) throw new Error("Failed to fetch saved jobs");
  return await res.json();
};