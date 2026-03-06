import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import {
  RuleQualityPairMetric,
  RuleQualityReportTaskResponse,
  RuleQualityResponse,
  RuleQualityService,
  RuleQualitySummary
} from '../services/rule-quality.service';

@Component({
  selector: 'app-rule-quality',
  standalone: true,
  imports: [CommonModule, RouterLink, SidebarComponent],
  templateUrl: './rule-quality.component.html'
})
export class RuleQualityComponent implements OnInit, OnDestroy {
  loading: boolean = true;
  polling: boolean = false;
  error: string | null = null;

  minSupport: number = 1;
  lookbackDays: number = 30;
  totalLabeledEvents: number = 0;
  freezeAt: string | null = null;
  pairMetrics: RuleQualityPairMetric[] = [];
  bestRules: RuleQualitySummary[] = [];
  worstRules: RuleQualitySummary[] = [];

  private reportId: number | null = null;
  private pollTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private pollAttempts: number = 0;
  private readonly pollIntervalMs = 1000;
  private readonly maxPollAttempts = 60;

  constructor(private ruleQualityService: RuleQualityService) {}

  ngOnInit(): void {
    this.loadRuleQuality(true);
  }

  ngOnDestroy(): void {
    this.clearPollTimeout();
  }

  loadRuleQuality(useConfiguredDefault: boolean = false, forceRefresh: boolean = false): void {
    this.loading = true;
    this.polling = false;
    this.error = null;
    this.clearPollTimeout();

    const lookbackDays = useConfiguredDefault ? null : this.lookbackDays;
    this.ruleQualityService.requestRuleQualityReport(this.minSupport, lookbackDays, forceRefresh).subscribe({
      next: (report) => {
        this.handleReportResponse(report);
      },
      error: () => {
        this.error = 'Failed to request rule quality report. Please try again.';
        this.loading = false;
        this.polling = false;
      }
    });
  }

  private handleReportResponse(report: RuleQualityReportTaskResponse): void {
    this.minSupport = report.minSupport;
    this.lookbackDays = report.lookbackDays;
    this.freezeAt = report.freezeAt;

    if (report.status === 'SUCCESS' && report.result) {
      this.applyResult(report.result);
      this.loading = false;
      this.polling = false;
      this.reportId = null;
      this.clearPollTimeout();
      return;
    }

    if (report.status === 'FAILURE') {
      this.error = report.error || 'Rule quality report generation failed.';
      this.loading = false;
      this.polling = false;
      this.reportId = null;
      this.clearPollTimeout();
      return;
    }

    this.reportId = report.reportId;
    this.polling = true;
    this.pollAttempts = 0;
    this.schedulePoll();
  }

  private schedulePoll(): void {
    this.clearPollTimeout();
    this.pollTimeoutId = setTimeout(() => this.pollReportStatus(), this.pollIntervalMs);
  }

  private pollReportStatus(): void {
    if (this.reportId === null) {
      return;
    }

    this.ruleQualityService.getRuleQualityReport(this.reportId).subscribe({
      next: (report) => {
        this.freezeAt = report.freezeAt;

        if (report.status === 'SUCCESS' && report.result) {
          this.applyResult(report.result);
          this.loading = false;
          this.polling = false;
          this.reportId = null;
          this.clearPollTimeout();
          return;
        }

        if (report.status === 'FAILURE') {
          this.error = report.error || 'Rule quality report generation failed.';
          this.loading = false;
          this.polling = false;
          this.reportId = null;
          this.clearPollTimeout();
          return;
        }

        this.pollAttempts += 1;
        if (this.pollAttempts >= this.maxPollAttempts) {
          this.error = 'Rule quality report timed out. Please refresh the report.';
          this.loading = false;
          this.polling = false;
          this.reportId = null;
          this.clearPollTimeout();
          return;
        }

        this.schedulePoll();
      },
      error: () => {
        this.error = 'Failed while polling report status. Please refresh the report.';
        this.loading = false;
        this.polling = false;
        this.reportId = null;
        this.clearPollTimeout();
      }
    });
  }

  private applyResult(response: RuleQualityResponse): void {
    this.totalLabeledEvents = response.totalLabeledEvents;
    this.lookbackDays = response.lookbackDays;
    this.freezeAt = response.freezeAt;
    this.pairMetrics = response.pairMetrics;
    this.bestRules = response.bestRules;
    this.worstRules = response.worstRules;
  }

  private clearPollTimeout(): void {
    if (this.pollTimeoutId !== null) {
      clearTimeout(this.pollTimeoutId);
      this.pollTimeoutId = null;
    }
  }

  refreshReport(): void {
    this.loadRuleQuality(false, true);
  }

  onMinSupportChange(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.minSupport = Number.isFinite(value) && value >= 1 ? Math.floor(value) : 1;
    this.loadRuleQuality();
  }

  onLookbackDaysChange(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.lookbackDays = Number.isFinite(value) && value >= 1 ? Math.floor(value) : 1;
    this.loadRuleQuality();
  }

  formatPercent(value: number | null): string {
    if (value === null) {
      return 'N/A';
    }
    return `${(value * 100).toFixed(1)}%`;
  }

  uniqueRulesCount(): number {
    const uniqueIds = new Set(this.pairMetrics.map(metric => metric.rId));
    return uniqueIds.size;
  }

  trackPair(index: number, metric: RuleQualityPairMetric): string {
    return `${metric.rId}-${metric.outcome}-${metric.label}-${index}`;
  }

  trackRule(_index: number, rule: RuleQualitySummary): number {
    return rule.rId;
  }
}
