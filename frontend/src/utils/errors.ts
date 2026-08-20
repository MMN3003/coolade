import { ApiError } from '@/api/client';

/** Extracts a user-facing Persian message from any thrown error. */
export function getErrorMessage(err: unknown, fallback = 'خطای غیرمنتظره‌ای رخ داد.'): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}
