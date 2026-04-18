// src/config.ts

<<<<<<< HEAD
export const API_BASE = "http://localhost:8000";
=======
export const API_BASE = import.meta.env.VITE_API_BASE;

// Utility function to construct API URLs
export const apiUrl = (endpoint: string) => `${API_BASE}${endpoint}`;

// Utility function to construct image URLs
export const imageUrl = (path: string) => `${API_BASE}${path}`;
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
