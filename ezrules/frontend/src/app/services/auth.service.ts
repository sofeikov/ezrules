import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, tap, catchError, throwError } from 'rxjs';
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
  last_login_at: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly AUTH_URL = `${environment.apiUrl}/api/v2/auth`;
  private readonly ACCESS_TOKEN_KEY = 'ezrules_access_token';
  private readonly REFRESH_TOKEN_KEY = 'ezrules_refresh_token';

  private loggedIn = new BehaviorSubject<boolean>(this.hasToken());
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
        this.loggedIn.next(true);
      })
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
        this.loggedIn.next(true);
      }),
      catchError(err => {
        this.logout();
        return throwError(() => err);
      })
    );
  }

  logout(): void {
    localStorage.removeItem(this.ACCESS_TOKEN_KEY);
    localStorage.removeItem(this.REFRESH_TOKEN_KEY);
    this.loggedIn.next(false);
    this.router.navigate(['/login']);
  }

  getCurrentUser(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${this.AUTH_URL}/me`);
  }
}
