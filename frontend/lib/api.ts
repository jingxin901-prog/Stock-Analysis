import type {
  InstrumentSearchResponse,
  MarketOverviewResponse,
  PortfolioRequest,
  PortfolioRobustnessRequest,
  PortfolioRobustnessResponse,
  PortfolioResponse,
  StockAnalysisResponse,
  StockExplanationResponse,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type StructuredApiError = {
  code?: string;
  message?: string;
  unavailable_symbols?: string[];
};

type ErrorTranslationKey =
  | "common.apiUnreachable"
  | "common.marketDataUnavailable"
  | "common.unknownError";

type ErrorTranslator = (
  key: ErrorTranslationKey,
  values?: Record<string, string | number>,
) => string;

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly unavailableSymbols: string[] = [],
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...init?.headers,
        },
      });
    } catch (reason: unknown) {
      lastError = reason;
      if (attempt === 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
    }
  }
  throw new ApiRequestError(
    lastError instanceof Error ? lastError.message : "Unable to reach the QuantAI API.",
    0,
    "api_unreachable",
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchApi(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string | { msg?: string }[] | StructuredApiError }
      | null;
    const detail = payload?.detail;
    const structured = detail && typeof detail === "object" && !Array.isArray(detail)
      ? detail
      : null;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg ?? "Validation error").join("; ")
      : typeof detail === "string"
        ? detail
        : structured?.message;
    throw new ApiRequestError(
      message ?? `API request failed with status ${response.status}.`,
      response.status,
      structured?.code,
      structured?.unavailable_symbols ?? [],
    );
  }
  return (await response.json()) as T;
}

export function getApiErrorMessage(reason: unknown, t: ErrorTranslator): string {
  if (reason instanceof ApiRequestError && reason.code === "api_unreachable") {
    return t("common.apiUnreachable");
  }
  if (reason instanceof ApiRequestError && reason.code === "market_data_unavailable") {
    return t("common.marketDataUnavailable", {
      symbols: reason.unavailableSymbols.join(", ") || "—",
    });
  }
  return reason instanceof Error ? reason.message : t("common.unknownError");
}

export function getMarketOverview(): Promise<MarketOverviewResponse> {
  return requestJson<MarketOverviewResponse>("/market/overview");
}

export function searchInstruments(query: string, limit = 8): Promise<InstrumentSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return requestJson<InstrumentSearchResponse>(`/instruments/search?${params.toString()}`);
}

export function getStockAnalysis(
  ticker: string,
  peers: string[] = [],
): Promise<StockAnalysisResponse> {
  const params = new URLSearchParams();
  if (peers.length) params.set("peers", peers.join("|"));
  const query = params.size ? `?${params.toString()}` : "";
  return requestJson<StockAnalysisResponse>(`/stocks/${encodeURIComponent(ticker)}${query}`);
}

export function getStockExplanation(
  ticker: string,
  locale: "en" | "zh-CN" = "en",
  peers: string[] = [],
): Promise<StockExplanationResponse> {
  const params = new URLSearchParams({ locale });
  if (peers.length) params.set("peers", peers.join("|"));
  return requestJson<StockExplanationResponse>(
    `/stocks/${encodeURIComponent(ticker)}/explanation?${params.toString()}`,
  );
}

export function optimizePortfolio(request: PortfolioRequest): Promise<PortfolioResponse> {
  return requestJson<PortfolioResponse>("/portfolio/optimize", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function analyzePortfolioRobustness(
  request: PortfolioRobustnessRequest,
): Promise<PortfolioRobustnessResponse> {
  return requestJson<PortfolioRobustnessResponse>("/portfolio/robustness", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
