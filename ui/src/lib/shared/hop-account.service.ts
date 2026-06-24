import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

export interface AccountInfo {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  organization_role?: string;
  organization_id?: string;
  organization_name?: string;
}

export interface AccountUpdate {
  email?: string;
  current_password?: string;
  new_password?: string;
}

export interface UpdateResponse {
  message: string;
  email: string;
}

@Injectable({ providedIn: 'root' })
export class HopAccountService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  private accountInfoSubject = new BehaviorSubject<AccountInfo | null>(null);
  public accountInfo$ = this.accountInfoSubject.asObservable();

  private isAdminSubject = new BehaviorSubject<boolean>(false);
  public isAdmin$ = this.isAdminSubject.asObservable();

  private isSuperuserSubject = new BehaviorSubject<boolean>(false);
  public isSuperuser$ = this.isSuperuserSubject.asObservable();

  getAccountInfo(): Observable<AccountInfo> {
    return this.http.get<AccountInfo>(`${this.apiUrl}/account/me`).pipe(
      tap(info => {
        this.accountInfoSubject.next(info);
        this.isAdminSubject.next(info.organization_role === 'admin');
        this.isSuperuserSubject.next(info.is_superuser === true);
      })
    );
  }

  updateAccount(data: AccountUpdate): Observable<UpdateResponse> {
    return this.http.put<UpdateResponse>(`${this.apiUrl}/account/me`, data);
  }

  deleteAccount(confirm: boolean = false): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiUrl}/account/me`, { body: { confirm } });
  }

  clearAccountInfo(): void {
    this.accountInfoSubject.next(null);
    this.isAdminSubject.next(false);
    this.isSuperuserSubject.next(false);
  }

  isAdmin(): boolean {
    return this.accountInfoSubject.value?.organization_role === 'admin' || false;
  }

  getCurrentEmail(): string | null {
    return this.accountInfoSubject.value?.email ?? null;
  }
}
