import { z } from 'zod';

export const RegistrationSchema = z.object({
  full_name: z
    .string()
    .min(2, 'Must be at least 2 characters')
    .max(100, 'Maximum 100 characters'),
  email: z
    .string()
    .email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Must be at least 8 characters')
    .max(128, 'Maximum 128 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter.')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter.')
    .regex(/[0-9]/, 'Password must contain at least one number.')
    .regex(/[^A-Za-z0-9]/, 'Password must contain at least one special character.'),
  confirm_password: z
    .string()
}).refine(data => data.password === data.confirm_password, {
  message: 'Passwords do not match.',
  path: ['confirm_password'],
});

export type RegistrationFormValues = z.infer<typeof RegistrationSchema>;

export const LoginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
});

export type LoginFormValues = z.infer<typeof LoginSchema>;
