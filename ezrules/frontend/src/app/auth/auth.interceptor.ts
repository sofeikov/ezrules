import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * HTTP interceptor that attaches JWT access token to all outgoing API requests.
 * On 401, attempts a token refresh and retries the original request once.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);

  // Don't attach token to login/refresh requests (avoid loops)
  if (req.url.includes('/auth/login') || req.url.includes('/auth/refresh')) {
    return next(req);
  }

  const token = authService.getAccessToken();
  let authReq = req;
  if (token) {
    authReq = req.clone({
      setHeaders: { Authorization: `Bearer ${token}` }
    });
  }

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !req.url.includes('/auth/')) {
        // Try to refresh the token
        return authService.refresh().pipe(
          switchMap(tokenResponse => {
            // Retry original request with new token
            const retryReq = req.clone({
              setHeaders: { Authorization: `Bearer ${tokenResponse.access_token}` }
            });
            return next(retryReq);
          }),
          catchError(refreshError => {
            // Refresh failed — force logout
            authService.logout();
            return throwError(() => refreshError);
          })
        );
      }
      return throwError(() => error);
    })
  );
};
