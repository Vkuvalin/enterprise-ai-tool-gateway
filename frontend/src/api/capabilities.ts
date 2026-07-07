import { apiRequest } from "./client";
import type { CapabilitiesResponse, HealthResponse } from "./types";

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}

export function getCapabilities(): Promise<CapabilitiesResponse> {
  return apiRequest<CapabilitiesResponse>("/capabilities");
}
