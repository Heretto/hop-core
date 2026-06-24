import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

export interface UserOrganizationInfo {
  id: string;
  name: string;
  slug: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at?: number;
  organizations?: UserOrganizationInfo[];
}

export interface SSOProviders {
  google: boolean;
  microsoft: boolean;
  sso_only: boolean;
  single_org_mode: boolean;
  google_client_id?: string;
}

interface User {
  id: string;
  email: string;
}

@Injectable({ providedIn: 'root' })
export class HopAuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private apiUrl = inject(HOP_API_URL);

  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  private loggedIn = false;
  private expiresAt: number | null = null;

  constructor() {
    if (sessionStorage.getItem('auth_active') === '1') {
      this.loggedIn = true;
      const exp = sessionStorage.getItem('auth_exp');
      this.expiresAt = exp ? Number(exp) : null;
    }
  }

  private setAuthState(expiresAt?: number): void {
    this.loggedIn = true;
    this.expiresAt = expiresAt ?? null;
    sessionStorage.setItem('auth_active', '1');
    if (expiresAt) sessionStorage.setItem('auth_exp', String(expiresAt));
  }

  private clearAuthState(): void {
    this.loggedIn = false;
    this.expiresAt = null;
    sessionStorage.removeItem('auth_active');
    sessionStorage.removeItem('auth_exp');
  }

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/auth/login`, { email, password }).pipe(
      tap((res) => this.setAuthState(res.expires_at))
    );
  }

  navigateToDashboard(returnUrl?: string): void {
    if (returnUrl) {
      try {
        const decoded = decodeURIComponent(returnUrl);
        if (decoded.startsWith('/') && !decoded.startsWith('//') && !decoded.includes('://')) {
          this.router.navigateByUrl(returnUrl);
          return;
        }
      } catch { /* fall through */ }
    }
    this.router.navigate(['/dashboard']);
  }

  updateTokens(response: { access_token: string; refresh_token: string; expires_at?: number }): void {
    this.setAuthState(response.expires_at);
  }

  register(email: string, password: string, organizationName?: string): Observable<any> {
    const payload: Record<string, string> = { email, password };
    if (organizationName) payload['organization_name'] = organizationName;
    return this.http.post(`${this.apiUrl}/auth/register`, payload);
  }

  logout(): void {
    this.http.post(`${this.apiUrl}/auth/logout`, {}).subscribe({ error: () => {} });
    this.clearAuthState();
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  refreshToken(): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/auth/refresh`, {}).pipe(
      tap((res) => this.setAuthState(res.expires_at))
    );
  }

  isAuthenticated(): boolean {
    if (!this.loggedIn) return false;
    if (this.expiresAt !== null && Date.now() / 1000 >= this.expiresAt) {
      this.clearAuthState();
      return false;
    }
    return true;
  }

  forgotPassword(email: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.apiUrl}/auth/forgot-password`, { email });
  }

  resetPassword(token: string, newPassword: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.apiUrl}/auth/reset-password`, {
      token,
      new_password: newPassword,
    });
  }

  getSSOProviders(): Observable<SSOProviders> {
    return this.http.get<SSOProviders>(`${this.apiUrl}/auth/sso/providers`);
  }

  loginWithGoogleToken(credential: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/auth/sso/google/token`, { credential }).pipe(
      tap((res) => this.setAuthState(res.expires_at))
    );
  }
}
