import type {
  HealthResponse,
  ConfigResponse,
  RunRequest,
  RunResponse,
  ReviewRequest,
  ReviewResponse,
  StatsResponse,
  RunRecord,
  ScoreRequest,
  ScoreResponse,
  BenchmarkRequest,
  BenchmarkResponse,
  ChatRequest,
  ChatApproveRequest,
  ChatResponse,
} from './types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    const err = new ApiError(res.status, body);
    throw err;
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  public status: number;
  public body: string;

  constructor(status: number, body: string) {
    super(`API ${status}: ${body}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export async function getConfig(): Promise<ConfigResponse> {
  return request<ConfigResponse>('/config');
}

export async function startRun(req: RunRequest): Promise<RunResponse> {
  return request<RunResponse>('/runs', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function submitReview(
  runId: string,
  req: ReviewRequest,
): Promise<ReviewResponse> {
  return request<ReviewResponse>(`/runs/${runId}/review`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getRuns(limit = 100): Promise<RunRecord[]> {
  return request<RunRecord[]>(`/runs?limit=${limit}`);
}

export async function getStats(): Promise<StatsResponse> {
  return request<StatsResponse>('/stats');
}

export async function scoreWhatIf(req: ScoreRequest): Promise<ScoreResponse> {
  return request<ScoreResponse>('/score', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function runBenchmark(
  req: BenchmarkRequest = {},
): Promise<BenchmarkResponse> {
  return request<BenchmarkResponse>('/benchmark', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function sendChatMessage(req: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(req),
    signal,
  });
}

export async function approveChatTool(req: ChatApproveRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/chat/approve', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function subscribeToRun(
  runId: string,
  handlers: {
    onRunStarted?: (data: string) => void;
    onScored?: (data: string) => void;
    onReviewRequired?: (data: string) => void;
    onReviewResolved?: (data: string) => void;
    onReviewTimeout?: (data: string) => void;
    onRunFinished?: (data: string) => void;
    onRunError?: (data: string) => void;
    onError?: (err: Event) => void;
  },
): EventSource {
  const es = new EventSource(`${BASE}/runs/${runId}/events`);

  const eventMap: Record<string, ((data: string) => void) | undefined> = {
    run_started: handlers.onRunStarted,
    scored: handlers.onScored,
    review_required: handlers.onReviewRequired,
    review_resolved: handlers.onReviewResolved,
    review_timeout: handlers.onReviewTimeout,
    run_finished: handlers.onRunFinished,
    run_error: handlers.onRunError,
  };

  for (const [evt, handler] of Object.entries(eventMap)) {
    if (handler) {
      es.addEventListener(evt, (e: MessageEvent) => {
        handler(e.data);
      });
    }
  }

  if (handlers.onError) {
    es.onerror = handlers.onError;
  }

  return es;
}
