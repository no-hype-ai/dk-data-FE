/**
 * Typed error hierarchy for dk-data-client.
 *
 * Every HTTP failure path from the server is translated into one of these
 * exceptions so consumers can branch on `instanceof`, not on status code.
 *
 * Mirrors `dk_data_client/errors.py` exactly.
 */

export class DkDataError extends Error {
  public readonly details: Record<string, unknown>;

  constructor(message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = "DkDataError";
    this.details = details ?? {};
    // Preserve prototype chain under transpilation.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 401 — missing, malformed, expired, or otherwise-invalid JWT. */
export class DkDataAuthError extends DkDataError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "DkDataAuthError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 403 — valid JWT but consumer lacks access to the target schema. */
export class DkDataForbiddenError extends DkDataError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "DkDataForbiddenError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 404 — the resource does not exist in dk-data. */
export class DkDataNotFoundError extends DkDataError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "DkDataNotFoundError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 410 — the resource exists but is marked stale. */
export class DkDataStaleError extends DkDataError {
  public readonly lastRefreshedAt: Date;

  constructor(
    message: string,
    opts: { lastRefreshedAt: Date; details?: Record<string, unknown> },
  ) {
    super(message, opts.details);
    this.name = "DkDataStaleError";
    this.lastRefreshedAt = opts.lastRefreshedAt;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Fallback to upstream failed. Raised only when `fallbackMode="upstream"`. */
export class DkDataUpstreamError extends DkDataError {
  public readonly upstream: string;

  constructor(
    message: string,
    opts: { upstream: string; details?: Record<string, unknown> },
  ) {
    super(message, opts.details);
    this.name = "DkDataUpstreamError";
    this.upstream = opts.upstream;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 429 — the metering proxy rate-limited this consumer. */
export class DkDataRateLimitError extends DkDataError {
  public readonly retryAfter: number;

  constructor(
    message: string,
    opts: { retryAfter: number; details?: Record<string, unknown> },
  ) {
    super(message, opts.details);
    this.name = "DkDataRateLimitError";
    this.retryAfter = opts.retryAfter;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 5xx — dk-data itself is broken. No automatic retry in v0.1. */
export class DkDataServerError extends DkDataError {
  public readonly statusCode: number;

  constructor(
    message: string,
    opts: { statusCode: number; details?: Record<string, unknown> },
  ) {
    super(message, opts.details);
    this.name = "DkDataServerError";
    this.statusCode = opts.statusCode;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
