const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Array<{ field: string; message: string }>,
    public requestId?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  const requestId = response.headers.get('x-request-id') || undefined;
  
  if (!response.ok) {
    let errorData: { error: { code: string; message: string; details?: Array<{ field: string; message: string }> } } | null = null;
    try {
      errorData = await response.json();
    } catch {
      // Ignore JSON parse errors
    }
    
    throw new ApiError(
      response.status,
      errorData?.error?.code || 'UNKNOWN_ERROR',
      errorData?.error?.message || response.statusText,
      errorData?.error?.details,
      requestId
    );
  }
  
  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }
  
  return response.json();
}

function getAuthHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  
  // Access token is stored in memory (via auth context)
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  
  return headers;
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      ...getAuthHeaders(),
      ...options.headers,
    },
    credentials: 'include', // Important for refresh token cookie
  });
  
  return handleResponse<T>(response);
}

// Auth API
export const authApi = {
  signup: (data: { email: string; password: string; full_name?: string; timezone?: string }) =>
    apiFetch<import('@/types/api').TokenResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  login: (data: { email: string; password: string }) =>
    apiFetch<import('@/types/api').TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  refresh: (refreshToken: string) =>
    apiFetch<import('@/types/api').TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
  
  logout: (refreshToken: string) =>
    apiFetch<import('@/types/api').OkResponse>('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
  
  logoutAll: () =>
    apiFetch<import('@/types/api').OkResponse>('/auth/logout-all', {
      method: 'POST',
    }),
  
  me: () =>
    apiFetch<import('@/types/api').UserOut>('/auth/me'),
  
  updateMe: (data: { full_name?: string; timezone?: string }) =>
    apiFetch<import('@/types/api').UserOut>('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  
  getPreferences: () =>
    apiFetch<import('@/types/api').UserPreferencesOut>('/auth/me/preferences'),
  
  updatePreferences: (data: { 
    default_reply_tone?: import('@/types/api').ReplyTone; 
    digest_enabled?: boolean; 
    timezone?: string; 
    notification_channels?: Record<string, unknown>; 
  }) =>
    apiFetch<import('@/types/api').UserPreferencesOut>('/auth/me/preferences', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  
  requestVerification: (email?: string) =>
    apiFetch<import('@/types/api').AuthMessage>('/auth/verify-email/request', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  
  confirmVerification: (token: string) =>
    apiFetch<import('@/types/api').AuthMessage>('/auth/verify-email/confirm', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  
  forgotPassword: (email: string) =>
    apiFetch<import('@/types/api').AuthMessage>('/auth/password/forgot', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  
  resetPassword: (token: string, newPassword: string) =>
    apiFetch<import('@/types/api').AuthMessage>('/auth/password/reset', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  
  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<import('@/types/api').AuthMessage>('/auth/password/change', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
};

// Email API
export const emailApi = {
  list: (params: import('@/types/api').EmailFilterParams = {}) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        if (Array.isArray(value)) {
          value.forEach(v => searchParams.append(key, String(v)));
        } else {
          searchParams.set(key, String(value));
        }
      }
    });
    return apiFetch<import('@/types/api').Page<import('@/types/api').EmailListItem>>(
      `/emails?${searchParams.toString()}`
    );
  },
  
  get: (id: number) =>
    apiFetch<import('@/types/api').EmailDetail>(`/emails/${id}`),
  
  create: (data: import('@/types/api').EmailCreate) =>
    apiFetch<import('@/types/api').EmailDetail>('/emails', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  update: (id: number, data: import('@/types/api').EmailUpdateRequest) =>
    apiFetch<import('@/types/api').EmailDetail>(`/emails/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  
  updateState: (id: number, data: import('@/types/api').StateUpdateRequest) =>
    apiFetch<import('@/types/api').EmailDetail>(`/emails/${id}/state`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  delete: (id: number) =>
    apiFetch<import('@/types/api').OkResponse>(`/emails/${id}`, {
      method: 'DELETE',
    }),
  
  restore: (id: number) =>
    apiFetch<import('@/types/api').EmailDetail>(`/emails/${id}/restore`, {
      method: 'POST',
    }),
  
  process: (id: number) =>
    apiFetch<import('@/types/api').EmailDetail>(`/emails/${id}/process`, {
      method: 'POST',
    }),
  
  importEml: (files: File[]) => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    return apiFetch<import('@/types/api').ImportSummary>('/emails/import/eml', {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set Content-Type with boundary
    });
  },
  
  importDataset: (file: File, processWithAi = false) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('process_with_ai', String(processWithAi));
    return apiFetch<import('@/types/api').ImportSummary>('/emails/import/dataset', {
      method: 'POST',
      body: formData,
      headers: {},
    });
  },
  
  exportCsv: (params: Pick<import('@/types/api').EmailFilterParams, 'q' | 'category'> = {}) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.set(key, String(value));
      }
    });
    return fetch(`${API_BASE}/emails/export.csv?${searchParams.toString()}`, {
      headers: getAuthHeaders(),
      credentials: 'include',
    }).then(res => {
      if (!res.ok) throw new Error('Export failed');
      return res.blob();
    });
  },
  
  listThreads: (page = 1, pageSize = 20, includeArchived = false) =>
    apiFetch<import('@/types/api').Page<import('@/types/api').ThreadListItem>>(
      `/threads?page=${page}&page_size=${pageSize}&include_archived=${includeArchived}`
    ),
  
  getThread: (id: number) =>
    apiFetch<import('@/types/api').ThreadDetail>(`/threads/${id}`),
};

// Smart Replies API
export const replyApi = {
  list: (params: { email_id?: number; status?: import('@/types/api').ReplyStatus; page?: number; page_size?: number } = {}) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value) !== '') {
        searchParams.set(key, String(value));
      }
    });
    return apiFetch<import('@/types/api').Page<import('@/types/api').SuggestedReplyOut>>(
      `/replies?${searchParams.toString()}`
    );
  },
  
  get: (id: number) =>
    apiFetch<import('@/types/api').SuggestedReplyOut>(`/replies/${id}`),
  
  create: (emailId: number, data: import('@/types/api').ReplyGenerateRequest) =>
    apiFetch<import('@/types/api').SuggestedReplyOut>(`/replies/email/${emailId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  update: (id: number, data: import('@/types/api').SuggestedReplyUpdate) =>
    apiFetch<import('@/types/api').SuggestedReplyOut>(`/replies/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  
  delete: (id: number) =>
    apiFetch<{ ok: boolean; message: string }>(`/replies/${id}`, {
      method: 'DELETE',
    }),
};

// Dashboard API
export const dashboardApi = {
  summary: () =>
    apiFetch<import('@/types/api').DashboardSummary>('/dashboard/summary'),
  
  counters: () =>
    apiFetch<import('@/types/api').DashboardCounters>('/dashboard/counters'),
  
  activity: (days = 30) =>
    apiFetch<import('@/types/api').ActivityPoint[]>(`/dashboard/activity?days=${days}`),
  
  categories: () =>
    apiFetch<import('@/types/api').CategoryCount[]>('/dashboard/categories'),
  
  sentiments: () =>
    apiFetch<import('@/types/api').SentimentCount[]>('/dashboard/sentiments'),
  
  priorities: () =>
    apiFetch<import('@/types/api').PriorityCount[]>('/dashboard/priorities'),
  
  recentEmails: (limit = 8) =>
    apiFetch<import('@/types/api').RecentEmail[]>(`/dashboard/recent-emails?limit=${limit}`),
  
  recentActivity: (limit = 10) =>
    apiFetch<import('@/types/api').RecentActivity[]>(`/dashboard/recent-activity?limit=${limit}`),
  
  deadlines: () =>
    apiFetch<import('@/types/api').DeadlineItem[]>('/dashboard/deadlines'),
  
  analytics: (dateFrom?: string, dateTo?: string) => {
    const params = new URLSearchParams();
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    return apiFetch<import('@/types/api').AnalyticsReport>(`/analytics?${params.toString()}`);
  },
};

// Assistant API
export const assistantApi = {
  listConversations: (page = 1, pageSize = 20) =>
    apiFetch<import('@/types/api').Page<import('@/types/api').AssistantConversationOut>>(
      `/assistant/conversations?page=${page}&page_size=${pageSize}`
    ),
  
  createConversation: (title?: string) =>
    apiFetch<import('@/types/api').AssistantConversationOut>('/assistant/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  
  getConversation: (id: number) =>
    apiFetch<import('@/types/api').AssistantConversationOut>(`/assistant/conversations/${id}`),
  
  deleteConversation: (id: number) =>
    apiFetch<{ ok: boolean; message: string }>(`/assistant/conversations/${id}`, {
      method: 'DELETE',
    }),
  
  ask: (conversationId: number, query: string) =>
    apiFetch<import('@/types/api').AssistantAnswer>(
      `/assistant/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        body: JSON.stringify({ query }),
      }
    ),
  
  queryOnce: (query: string) =>
    apiFetch<import('@/types/api').AssistantAnswer>('/assistant/query', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
};

// Notifications API
export const notificationApi = {
  list: (page = 1, pageSize = 20, unreadOnly = false) =>
    apiFetch<import('@/types/api').PaginatedNotifications>(
      `/notifications?page=${page}&page_size=${pageSize}&unread_only=${unreadOnly}`
    ),
  
  markRead: (id: number) =>
    apiFetch<import('@/types/api').NotificationOut>(`/notifications/${id}/read`, {
      method: 'POST',
    }),
  
  markAllRead: () =>
    apiFetch<{ ok: boolean; count: number }>('/notifications/read-all', {
      method: 'POST',
    }),
};

export { ApiError };