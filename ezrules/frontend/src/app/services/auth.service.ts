import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, tap, catchError, throwError, of } from 'rxjs';
import { finalize, map, shareReplay, switchMap } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthUser {
  id: number;
  email: string;
  active: boolean;
  roles: { id: number; name: string; description: string | null }[];
  permissions: string[];
  last_login_at: string | null;
}

export interface MessageResponse {
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly AUTH_URL = `${environment.apiUrl}/api/v2/auth`;
  private readonly ACCESS_TOKEN_KEY = 'ezrules_access_token';
  private readonly REFRESH_TOKEN_KEY = 'ezrules_refresh_token';

  private loggedIn = new BehaviorSubject<boolean>(this.hasToken());
  private currentUser = new BehaviorSubject<AuthUser | null>(null);
  private currentUserRequest$: Observable<AuthUser> | null = null;
  isLoggedIn$ = this.loggedIn.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  private hasToken(): boolean {
    return !!localStorage.getItem(this.ACCESS_TOKEN_KEY);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(this.ACCESS_TOKEN_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(this.REFRESH_TOKEN_KEY);
  }

  getCurrentUserSnapshot(): AuthUser | null {
    return this.currentUser.value;
  }

  private setCurrentUser(user: AuthUser | null): void {
    this.currentUser.next(user);
  }

  login(email: string, password: string): Observable<TokenResponse> {
    // Backend expects OAuth2 form data (username + password)
    const formData = new URLSearchParams();
    formData.set('username', email);
    formData.set('password', password);

    return this.http.post<TokenResponse>(`${this.AUTH_URL}/login`, formData.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    }).pipe(
      tap(response => {
        localStorage.setItem(this.ACCESS_TOKEN_KEY, response.access_token);
        localStorage.setItem(this.REFRESH_TOKEN_KEY, response.refresh_token);
        this.setCurrentUser(null);
        this.currentUserRequest$ = null;
        this.loggedIn.next(true);
      }),
      switchMap((response) => this.http.get<AuthUser>(`${this.AUTH_URL}/me`).pipe(
        tap((user) => this.setCurrentUser(user)),
        map(() => response),
        catchError(() => of(response))
      ))
    );
  }

  refresh(): Observable<TokenResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      return throwError(() => new Error('No refresh token'));
    }

    return this.http.post<TokenResponse>(`${this.AUTH_URL}/refresh`, {
      refresh_token: refreshToken
    }).pipe(
      tap(response => {
        localStorage.setItem(this.ACCESS_TOKEN_KEY, response.access_token);
        localStorage.setItem(this.REFRESH_TOKEN_KEY, response.refresh_token);
        this.currentUserRequest$ = null;
        this.loggedIn.next(true);
      }),
      catchError(err => {
        this.logout();
        return throwError(() => err);
      })
    );
  }

  logout(): void {
    const refreshToken = this.getRefreshToken();
    if (refreshToken) {
      // Fire and forget — clear local state regardless of outcome
      this.http.post(`${this.AUTH_URL}/logout`, { refresh_token: refreshToken }).subscribe({
        error: () => {} // Ignore errors — local cleanup always happens
      });
    }
    localStorage.removeItem(this.ACCESS_TOKEN_KEY);
    localStorage.removeItem(this.REFRESH_TOKEN_KEY);
    this.setCurrentUser(null);
    this.currentUserRequest$ = null;
    this.loggedIn.next(false);
    this.router.navigate(['/login']);
  }

  getCurrentUser(forceRefresh: boolean = false): Observable<AuthUser> {
    if (!forceRefresh) {
      const cachedUser = this.currentUser.value;
      if (cachedUser) {
        return of(cachedUser);
      }
      if (this.currentUserRequest$) {
        return this.currentUserRequest$;
      }
    }

    this.currentUserRequest$ = this.http.get<AuthUser>(`${this.AUTH_URL}/me`).pipe(
      tap(user => this.setCurrentUser(user)),
      catchError((error) => {
        if (error.status === 401) {
          this.setCurrentUser(null);
        }
        return throwError(() => error);
      }),
      finalize(() => {
        this.currentUserRequest$ = null;
      }),
      shareReplay(1)
    );

    return this.currentUserRequest$;
  }

  hasPermission(permission: string): Observable<boolean> {
    return this.getCurrentUser().pipe(
      map(user => user.permissions.includes(permission))
    );
  }

  acceptInvite(token: string, password: string): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.AUTH_URL}/accept-invite`, { token, password });
  }

  forgotPassword(email: string): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.AUTH_URL}/forgot-password`, { email });
  }

  resetPassword(token: string, password: string): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.AUTH_URL}/reset-password`, { token, password });
  }
}
