import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface AlertRule {
  id: number;
  name: string;
  outcome: string;
  threshold: number;
  window_seconds: number;
  cooldown_seconds: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertIncident {
  id: number;
  alert_rule_id: number;
  outcome: string;
  observed_count: number;
  threshold: number;
  window_start: string;
  window_end: string;
  status: string;
  triggered_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export interface InAppNotification {
  id: number;
  severity: string;
  title: string;
  body: string;
  action_url: string | null;
  source_type: string;
  source_id: number;
  created_at: string;
  read_at: string | null;
}

export interface AlertRulePayload {
  name: string;
  outcome: string;
  threshold: number;
  window_seconds: number;
  cooldown_seconds: number;
  enabled: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class AlertService {
  private apiUrl = `${environment.apiUrl}/api/v2`;

  constructor(private http: HttpClient) {}

  getAlertRules(): Observable<{ rules: AlertRule[] }> {
    return this.http.get<{ rules: AlertRule[] }>(`${this.apiUrl}/alerts/rules`);
  }

  createAlertRule(payload: AlertRulePayload): Observable<{ success: boolean; message: string; rule: AlertRule }> {
    return this.http.post<{ success: boolean; message: string; rule: AlertRule }>(`${this.apiUrl}/alerts/rules`, payload);
  }

  updateAlertRule(ruleId: number, payload: Partial<AlertRulePayload>): Observable<{ success: boolean; message: string; rule: AlertRule }> {
    return this.http.patch<{ success: boolean; message: string; rule: AlertRule }>(`${this.apiUrl}/alerts/rules/${ruleId}`, payload);
  }

  getAlertIncidents(limit = 50): Observable<{ incidents: AlertIncident[] }> {
    return this.http.get<{ incidents: AlertIncident[] }>(`${this.apiUrl}/alerts/incidents`, { params: { limit } });
  }

  acknowledgeIncident(incidentId: number): Observable<{ success: boolean; message: string; incident: AlertIncident }> {
    return this.http.post<{ success: boolean; message: string; incident: AlertIncident }>(
      `${this.apiUrl}/alerts/incidents/${incidentId}/acknowledge`,
      {},
    );
  }

  getNotifications(unreadOnly = false, limit = 10): Observable<{ notifications: InAppNotification[] }> {
    return this.http.get<{ notifications: InAppNotification[] }>(`${this.apiUrl}/notifications`, {
      params: { unread_only: unreadOnly, limit },
    });
  }

  getUnreadCount(): Observable<{ unread_count: number }> {
    return this.http.get<{ unread_count: number }>(`${this.apiUrl}/notifications/unread-count`);
  }

  markNotificationRead(notificationId: number): Observable<{ unread_count: number }> {
    return this.http.post<{ unread_count: number }>(`${this.apiUrl}/notifications/${notificationId}/read`, {});
  }

  markAllNotificationsRead(): Observable<{ unread_count: number }> {
    return this.http.post<{ unread_count: number }>(`${this.apiUrl}/notifications/read-all`, {});
  }
}
