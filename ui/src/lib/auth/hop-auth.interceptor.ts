import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { HopAuthService } from './hop-auth.service';

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

export const hopAuthInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(HopAuthService);

  const csrfToken = getCookie('csrf_token');
  const headers: Record<string, string> = {};
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  req = req.clone({ withCredentials: true, setHeaders: headers });

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !req.url.includes('/auth/refresh') && !req.url.includes('/auth/login')) {
        return authService.refreshToken().pipe(
          switchMap(() => next(req.clone({ withCredentials: true }))),
          catchError(refreshError => {
            authService.logout();
            return throwError(() => refreshError);
          })
        );
      }
      return throwError(() => error);
    })
  );
};
