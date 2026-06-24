import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { HopAuthService } from './hop-auth.service';

function isSafeReturnUrl(url: string): boolean {
  try {
    const decoded = decodeURIComponent(url);
    return decoded.startsWith('/') && !decoded.startsWith('//') && !decoded.includes('://');
  } catch {
    return false;
  }
}

export const hopAuthGuard: CanActivateFn = (_route, state) => {
  const authService = inject(HopAuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) return true;

  const returnUrl = isSafeReturnUrl(state.url) ? state.url : '/dashboard';
  router.navigate(['/login'], { queryParams: { returnUrl } });
  return false;
};
