import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { UserListService, UserListItem, UserListDetail } from '../services/user-list.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-user-lists',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './user-lists.component.html'
})
export class UserListsComponent implements OnInit {
  lists: UserListItem[] = [];
  selectedList: UserListDetail | null = null;
  newListName: string = '';
  newEntryValue: string = '';

  loading: boolean = true;
  entriesLoading: boolean = false;
  error: string | null = null;
  createListError: string | null = null;
  deleteListError: string | null = null;
  createEntryError: string | null = null;
  deleteEntryError: string | null = null;

  constructor(private userListService: UserListService) { }

  ngOnInit(): void {
    this.loadLists();
  }

  loadLists(): void {
    this.loading = true;
    this.error = null;

    this.userListService.getUserLists().subscribe({
      next: (lists) => {
        this.lists = lists;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load user lists. Please try again.';
        this.loading = false;
      }
    });
  }

  createList(): void {
    if (!this.newListName.trim()) return;

    this.createListError = null;
    this.userListService.createUserList(this.newListName.trim()).subscribe({
      next: (response) => {
        if (response.success) {
          this.newListName = '';
          this.loadLists();
        } else {
          this.createListError = response.error ?? 'Failed to create list.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.createListError = err.error?.error ?? 'Failed to create list. Please try again.';
      }
    });
  }

  deleteList(listId: number, listName: string): void {
    if (!confirm(`Are you sure you want to delete list "${listName}" and all its entries?`)) return;

    this.deleteListError = null;
    this.userListService.deleteUserList(listId).subscribe({
      next: () => {
        if (this.selectedList?.id === listId) {
          this.selectedList = null;
        }
        this.loadLists();
      },
      error: () => {
        this.deleteListError = `Failed to delete list "${listName}". Please try again.`;
      }
    });
  }

  selectList(listId: number): void {
    this.entriesLoading = true;
    this.createEntryError = null;
    this.deleteEntryError = null;
    this.newEntryValue = '';

    this.userListService.getUserListDetail(listId).subscribe({
      next: (detail) => {
        this.selectedList = detail;
        this.entriesLoading = false;
      },
      error: () => {
        this.entriesLoading = false;
      }
    });
  }

  addEntry(): void {
    if (!this.newEntryValue.trim() || !this.selectedList) return;

    this.createEntryError = null;
    this.userListService.addEntry(this.selectedList.id, this.newEntryValue.trim()).subscribe({
      next: (response) => {
        if (response.success) {
          this.newEntryValue = '';
          this.selectList(this.selectedList!.id);
          this.loadLists();
        } else {
          this.createEntryError = response.error ?? 'Failed to add entry.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.createEntryError = err.error?.error ?? 'Failed to add entry. Please try again.';
      }
    });
  }

  deleteEntry(entryId: number, entryValue: string): void {
    if (!this.selectedList) return;
    if (!confirm(`Are you sure you want to delete entry "${entryValue}"?`)) return;

    this.deleteEntryError = null;
    const listId = this.selectedList.id;
    this.userListService.deleteEntry(listId, entryId).subscribe({
      next: () => {
        this.selectList(listId);
        this.loadLists();
      },
      error: () => {
        this.deleteEntryError = `Failed to delete entry "${entryValue}". Please try again.`;
      }
    });
  }
}
