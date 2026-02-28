import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiKeyItem, ApiKeyService, CreateApiKeyResponse } from '../services/api-key.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-api-keys',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './api-keys.component.html',
})
export class ApiKeysComponent implements OnInit {
  keys: ApiKeyItem[] = [];
  loading = true;
  error: string | null = null;

  // Create dialog
  showCreateDialog = false;
  newLabel = '';
  creating = false;
  createError: string | null = null;

  // Raw key reveal dialog (shown once after creation)
  showKeyRevealDialog = false;
  createdRawKey = '';
  createdLabel = '';
  copied = false;

  // Revoke
  revokeError: string | null = null;

  constructor(private apiKeyService: ApiKeyService) {}

  ngOnInit(): void {
    this.loadKeys();
  }

  loadKeys(): void {
    this.loading = true;
    this.error = null;
    this.apiKeyService.list().subscribe({
      next: keys => {
        this.keys = keys;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load API keys. Please try again.';
        this.loading = false;
      },
    });
  }

  openCreateDialog(): void {
    this.newLabel = '';
    this.createError = null;
    this.showCreateDialog = true;
  }

  closeCreateDialog(): void {
    this.showCreateDialog = false;
  }

  submitCreate(): void {
    if (!this.newLabel.trim()) return;
    this.creating = true;
    this.createError = null;
    this.apiKeyService.create(this.newLabel.trim()).subscribe({
      next: (resp: CreateApiKeyResponse) => {
        this.creating = false;
        this.showCreateDialog = false;
        this.createdRawKey = resp.raw_key;
        this.createdLabel = resp.label;
        this.copied = false;
        this.showKeyRevealDialog = true;
        this.loadKeys();
      },
      error: (err) => {
        this.creating = false;
        this.createError = err.error?.detail || 'Failed to create API key. Please try again.';
      },
    });
  }

  closeKeyRevealDialog(): void {
    this.showKeyRevealDialog = false;
    this.createdRawKey = '';
  }

  copyKey(): void {
    navigator.clipboard.writeText(this.createdRawKey).then(() => {
      this.copied = true;
      setTimeout(() => { this.copied = false; }, 2000);
    });
  }

  revokeKey(key: ApiKeyItem): void {
    if (!confirm(`Revoke API key "${key.label}"?\n\nThis action cannot be undone. Any service using this key will receive 401 errors.`)) {
      return;
    }
    this.revokeError = null;
    this.apiKeyService.revoke(key.gid).subscribe({
      next: () => this.loadKeys(),
      error: (err) => {
        this.revokeError = err.error?.detail || `Failed to revoke key "${key.label}". Please try again.`;
      },
    });
  }

  formatDate(dateStr: string | null): string {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString();
  }
}
