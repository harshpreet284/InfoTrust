import { apiClient } from '../lib/axios';
import type { RegistrationFormValues, LoginFormValues } from '../schemas/auth.schema';

export interface UserOut {
  id: string;
  full_name: string;
  email: string;
  role: string;
  created_at: string;
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

export const authService = {
  async register(payload: RegistrationFormValues): Promise<RegistrationSuccessResponse> {
    const response = await apiClient.post<RegistrationSuccessResponse>('/auth/register', payload);
    return response.data;
  },
  async login(payload: LoginFormValues): Promise<LoginSuccessResponse> {
    const response = await apiClient.post<LoginSuccessResponse>('/auth/login', payload);
    return response.data;
  },
};
