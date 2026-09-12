import { apiClient } from '../lib/axios';
import type { RegistrationFormValues } from '../schemas/auth.schema';

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

export const authService = {
  async register(payload: RegistrationFormValues): Promise<RegistrationSuccessResponse> {
    const response = await apiClient.post<RegistrationSuccessResponse>('/auth/register', payload);
    return response.data;
  },
};
