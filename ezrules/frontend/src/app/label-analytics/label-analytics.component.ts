import { Component, OnInit, OnDestroy, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Chart, registerables } from 'chart.js';
import { LabelAnalyticsService, LabelDataset } from '../services/label-analytics.service';
import { SidebarComponent } from '../components/sidebar.component';

Chart.register(...registerables);

@Component({
  selector: 'app-label-analytics',
  standalone: true,
  imports: [CommonModule, SidebarComponent],
  templateUrl: './label-analytics.component.html'
})
export class LabelAnalyticsComponent implements OnInit, AfterViewInit, OnDestroy {
  totalLabeled: number = 0;
  loading: boolean = true;
  chartsLoading: boolean = true;
  error: string | null = null;
  selectedAggregation: string = '6h';
  datasets: LabelDataset[] = [];
  timeLabels: string[] = [];

  private charts: Map<string, Chart> = new Map();
  private canvasReady = false;

  readonly aggregations = [
    { value: '1h', label: 'Last 1 Hour' },
    { value: '6h', label: 'Last 6 Hours' },
    { value: '12h', label: 'Last 12 Hours' },
    { value: '24h', label: 'Last 24 Hours' },
    { value: '30d', label: 'Last 30 Days' }
  ];

  constructor(private labelAnalyticsService: LabelAnalyticsService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.loadSummary();
    this.loadDistribution();
  }

  ngAfterViewInit(): void {
    this.canvasReady = true;
    if (this.datasets.length > 0) {
      this.cdr.detectChanges();
      setTimeout(() => this.renderCharts(), 0);
    }
  }

  ngOnDestroy(): void {
    this.destroyCharts();
  }

  loadSummary(): void {
    this.labelAnalyticsService.getSummary().subscribe({
      next: (response) => {
        this.totalLabeled = response.total_labeled;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load label summary. Please try again.';
        this.loading = false;
      }
    });
  }

  loadDistribution(): void {
    this.chartsLoading = true;
    this.labelAnalyticsService.getDistribution(this.selectedAggregation).subscribe({
      next: (response) => {
        this.timeLabels = response.labels;
        this.datasets = response.datasets;
        this.chartsLoading = false;
        if (this.canvasReady) {
          this.cdr.detectChanges();
          setTimeout(() => this.renderCharts(), 0);
        }
      },
      error: () => {
        this.error = 'Failed to load label distribution. Please try again.';
        this.chartsLoading = false;
      }
    });
  }

  onAggregationEvent(event: Event): void {
    this.selectedAggregation = (event.target as HTMLSelectElement).value;
    this.loadDistribution();
  }

  private renderCharts(): void {
    this.destroyCharts();
    this.datasets.forEach((dataset, idx) => {
      const canvas = document.getElementById(`labelChart_${idx}`) as HTMLCanvasElement;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: this.timeLabels,
          datasets: [{
            label: dataset.label,
            data: dataset.data,
            borderColor: dataset.borderColor,
            backgroundColor: dataset.backgroundColor,
            tension: 0.3,
            fill: true
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: false },
            title: { display: false }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { precision: 0 }
            },
            x: {
              ticks: { maxRotation: 45, minRotation: 45 }
            }
          }
        }
      });
      this.charts.set(dataset.label, chart);
    });
  }

  private destroyCharts(): void {
    this.charts.forEach(chart => chart.destroy());
    this.charts.clear();
  }
}
