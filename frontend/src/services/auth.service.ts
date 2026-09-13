import { apiClient } from '../lib/axios';
import type { RegistrationFormValues, LoginFormValues } from '../schemas/auth.schema';

export interface UserOut {
  id: string;
  full_name: string;
  email: string;
  role: string;
  created_at: string;
  is_active?: boolean;
}

export interface RegistrationSuccessResponse {
  success: boolean;
  message: string;
  data: UserOut;
}

export interface LoginDataOut {
  access_token: string;
  refresh_token: string;
  user: UserOut;
}

export interface LoginSuccessResponse {
  success: boolean;
  message: string;
  data: LoginDataOut;
}

export interface RefreshDataOut {
  access_token: string;
  refresh_token: string;
}

export interface RefreshSuccessResponse {
  success: boolean;
  message: string;
  data: RefreshDataOut;
}

export interface LogoutSuccessResponse {
  success: boolean;
  message: string;
  data: Record<string, never>;
}

export interface CurrentUserSuccessResponse {
  success: boolean;
  message: string;
  data: UserOut;
}

export const authService = {
  async register(payload: RegistrationFormValues): Promise<RegistrationSuccessResponse> {
    const response = await apiClient.post<RegistrationSuccessResponse>('/auth/register', payload);
    return response.data;
  },

  async login(payload: LoginFormValues): Promise<LoginSuccessResponse> {
    const response = await apiClient.post<LoginSuccessResponse>('/auth/login', payload);
    return response.data;
  },

  async logout(refreshToken: string): Promise<LogoutSuccessResponse> {
    const response = await apiClient.post<LogoutSuccessResponse>('/auth/logout', { refresh_token: refreshToken });
    return response.data;
  },

  async refreshToken(refreshToken: string): Promise<RefreshSuccessResponse> {
    const response = await apiClient.post<RefreshSuccessResponse>('/auth/refresh', { refresh_token: refreshToken });
    return response.data;
  },

  async getCurrentUser(): Promise<CurrentUserSuccessResponse> {
    const response = await apiClient.get<CurrentUserSuccessResponse>('/auth/me');
    return response.data;
  },
};
