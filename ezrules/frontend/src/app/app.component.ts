import { CommonModule } from '@angular/common';
import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationStart, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet],
  template: `
    <div
      *ngIf="navigating"
      class="fixed inset-0 z-50 flex items-center justify-center bg-gray-50/70 backdrop-blur-sm pointer-events-none"
      aria-hidden="true"
    >
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
    </div>

    <router-outlet></router-outlet>
  `
})
export class AppComponent {
  title = 'ezrules-frontend';
  navigating = false;
  private readonly destroyRef = inject(DestroyRef);

  constructor(private router: Router) {
    this.router.events.pipe(
      filter((event) =>
        event instanceof NavigationStart ||
        event instanceof NavigationEnd ||
        event instanceof NavigationCancel ||
        event instanceof NavigationError
      ),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe((event) => {
      this.navigating = event instanceof NavigationStart;
    });
  }
}
