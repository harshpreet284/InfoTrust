import axios, { AxiosError } from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import { tokenStorage } from './token-storage';

// Use environment variable with fallback to local backend for development
const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Concurrency state
let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: any) => void }> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token as string);
    }
  });
  failedQueue = [];
};

interface RetryableAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

// Response Interceptor
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableAxiosRequestConfig;

    // Check if the error is a 401 and not explicitly excluded
    if (
      !originalRequest ||
      error.response?.status !== 401 ||
      originalRequest._retry ||
      originalRequest.url === '/auth/login' ||
      originalRequest.url === '/auth/register' ||
      originalRequest.url === '/auth/refresh' ||
      originalRequest.url === '/auth/logout'
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Single-flight: queue this request and wait for the refresh promise to resolve
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return apiClient(originalRequest);
        })
        .catch((err) => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) {
      isRefreshing = false;
      window.dispatchEvent(new Event('auth:unauthorized'));
      return Promise.reject(error);
    }

    const startingGeneration = tokenStorage.getGeneration();

    try {
      // Bypass interceptors using raw axios
      const response = await axios.post(`${baseURL}/auth/refresh`, { refresh_token: refreshToken });

      // Verify session hasn't been altered (e.g. by logout) during this request
      if (tokenStorage.getGeneration() !== startingGeneration) {
        throw new Error('Session epoch mismatch');
      }

      const { access_token, refresh_token } = response.data.data;
      tokenStorage.setTokens(access_token, refresh_token);

      processQueue(null, access_token);

      originalRequest.headers.Authorization = `Bearer ${access_token}`;
      return apiClient(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);

      // Only clear if the generation still matches (prevents clearing a newly logged-in session's tokens)
      if (tokenStorage.getGeneration() === startingGeneration) {
        tokenStorage.clearTokens();
      }

      window.dispatchEvent(new Event('auth:unauthorized'));
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
