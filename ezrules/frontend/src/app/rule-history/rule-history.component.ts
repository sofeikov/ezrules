import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { diffLines, Change } from 'diff';
import { RuleHistoryEntry, RuleService } from '../services/rule.service';
import { SidebarComponent } from '../components/sidebar.component';

export interface DiffPair {
  fromEntry: RuleHistoryEntry;
  toEntry: RuleHistoryEntry;
  changes: Change[];
}

@Component({
  selector: 'app-rule-history',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  templateUrl: './rule-history.component.html'
})
export class RuleHistoryComponent implements OnInit {
  ruleId: number | null = null;
  rid: string = '';
  history: RuleHistoryEntry[] = [];
  diffPairs: DiffPair[] = [];
  loading: boolean = true;
  error: string | null = null;

  constructor(
    private route: ActivatedRoute,
    private ruleService: RuleService
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.ruleId = parseInt(id, 10);
      this.loadHistory(this.ruleId);
    }
  }

  loadHistory(ruleId: number): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRuleHistory(ruleId).subscribe({
      next: (response) => {
        this.rid = response.rid;
        this.history = response.history;
        this.diffPairs = this.computeDiffs(response.history);
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load rule history.';
        this.loading = false;
      }
    });
  }

  computeDiffs(history: RuleHistoryEntry[]): DiffPair[] {
    const pairs: DiffPair[] = [];
    for (let i = 1; i < history.length; i++) {
      const fromEntry = history[i - 1];
      const toEntry = history[i];
      const changes = diffLines(fromEntry.logic, toEntry.logic);
      pairs.push({ fromEntry, toEntry, changes });
    }
    // Return newest-first so the timeline shows most recent diff at the top
    return pairs.reverse();
  }

  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }

  hasChanges(changes: Change[]): boolean {
    return changes.some(c => c.added || c.removed);
  }
}
