import { InjectionToken } from '@angular/core';

/** Base URL for the hop-core API (e.g. '/api/v1' or 'https://api.example.com/api/v1'). */
export const HOP_API_URL = new InjectionToken<string>('HOP_API_URL', {
  factory: () => '/api/v1',
});
