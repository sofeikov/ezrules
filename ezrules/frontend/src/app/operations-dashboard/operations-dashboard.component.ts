import { AfterViewInit, ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Chart, registerables } from 'chart.js';
import { SidebarComponent } from '../components/sidebar.component';
import {
  OperationsDashboardService,
  OperationsSummaryResponse
} from '../services/operations-dashboard.service';

Chart.register(...registerables);

@Component({
  selector: 'app-operations-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, SidebarComponent],
  templateUrl: './operations-dashboard.component.html'
})
export class OperationsDashboardComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly periods = [
    { days: 7, label: 'Last 7 days' },
    { days: 30, label: 'Last 30 days' },
    { days: 90, label: 'Last 90 days' }
  ];

  selectedDays = 30;
  data: OperationsSummaryResponse | null = null;
  loading = true;
  error: string | null = null;

  private chart: Chart | null = null;
  private canvasReady = false;
  private requestId = 0;

  constructor(
    private readonly operationsService: OperationsDashboardService,
    private readonly cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadSummary();
  }

  ngAfterViewInit(): void {
    this.canvasReady = true;
    this.renderChartWhenReady();
  }

  ngOnDestroy(): void {
    this.destroyChart();
  }

  loadSummary(): void {
    const currentRequestId = ++this.requestId;
    this.loading = true;
    this.error = null;
    this.operationsService.getSummary(this.selectedDays).subscribe({
      next: (response) => {
        if (currentRequestId !== this.requestId) {
          return;
        }
        this.data = response;
        this.loading = false;
        this.renderChartWhenReady();
      },
      error: () => {
        if (currentRequestId !== this.requestId) {
          return;
        }
        this.error = 'Failed to load operations data.';
        this.loading = false;
        this.destroyChart();
      }
    });
  }

  formatRate(value: number | null): string {
    return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
  }

  formatAge(totalSeconds: number): string {
    const totalHours = Math.floor(totalSeconds / 3600);
    const days = Math.floor(totalHours / 24);
    const hours = totalHours % 24;
    if (days > 0) {
      return `${days}d ${hours}h`;
    }
    if (totalHours > 0) {
      return `${totalHours}h`;
    }
    return '<1h';
  }

  private renderChartWhenReady(): void {
    if (!this.canvasReady || this.loading || !this.data) {
      return;
    }
    this.cdr.detectChanges();
    setTimeout(() => this.renderChart(), 0);
  }

  private renderChart(): void {
    this.destroyChart();
    const canvas = document.getElementById('operationsCaseFlowChart') as HTMLCanvasElement | null;
    if (!canvas || !this.data || this.data.case_flow.length === 0) {
      return;
    }
    this.chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: this.data.case_flow.map(point => point.date),
        datasets: [
          {
            label: 'Opened',
            data: this.data.case_flow.map(point => point.opened),
            backgroundColor: 'rgba(96, 165, 250, 0.8)',
            borderColor: 'rgb(59, 130, 246)',
            borderWidth: 1,
            borderRadius: 3
          },
          {
            label: 'Resolved',
            data: this.data.case_flow.map(point => point.resolved),
            backgroundColor: 'rgba(52, 211, 153, 0.8)',
            borderColor: 'rgb(16, 185, 129)',
            borderWidth: 1,
            borderRadius: 3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
          x: { ticks: { maxTicksLimit: 10 } }
        },
        plugins: {
          legend: { position: 'bottom' }
        }
      }
    });
  }

  private destroyChart(): void {
    this.chart?.destroy();
    this.chart = null;
  }
}
