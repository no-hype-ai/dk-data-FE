# Admin App Graceful Degradation Patterns

**Feature**: 006-006-admin-integration
**Purpose**: Document implementation patterns for Admin App resilience when dk-data is unavailable
**Target Repository**: `/Users/nicholas/Code/behavior-labs-ai`

## Overview

These patterns improve the Admin App Compass user experience when the dk-data PostgREST service is unavailable, providing clear status indicators and friendly error messages instead of raw 503 errors.

---

## Pattern 1: PostgREST Client Health Check Caching

**File**: `apps/admin/lib/compass/postgrest-client.ts`

### Implementation

```typescript
export class PostgRESTClient {
  private baseUrl: string;
  private healthCheckCache: { status: boolean; timestamp: number } | null = null;
  private readonly HEALTH_CACHE_TTL = 30000; // 30 seconds

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /**
   * Check if dk-data service is available with caching.
   * Caches result for 30 seconds to prevent excessive API calls.
   */
  async isAvailable(): Promise<boolean> {
    // Check cache first
    if (
      this.healthCheckCache &&
      Date.now() - this.healthCheckCache.timestamp < this.HEALTH_CACHE_TTL
    ) {
      return this.healthCheckCache.status;
    }

    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000), // 5 second timeout
      });
      const status = response.ok;
      this.healthCheckCache = { status, timestamp: Date.now() };
      return status;
    } catch {
      this.healthCheckCache = { status: false, timestamp: Date.now() };
      return false;
    }
  }

  /**
   * Clear the health check cache (e.g., after manual retry).
   */
  clearHealthCache(): void {
    this.healthCheckCache = null;
  }

  /**
   * Search molecules with graceful unavailability handling.
   */
  async searchMolecules(query: string): Promise<SearchResult> {
    if (!(await this.isAvailable())) {
      return {
        status: 'unavailable',
        message: 'Molecule database is currently unavailable',
        results: [],
      };
    }

    try {
      const response = await fetch(
        `${this.baseUrl}/molecules?name=ilike.*${encodeURIComponent(query)}*`,
        {
          headers: this.getAuthHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      return {
        status: 'success',
        results: data,
      };
    } catch (error) {
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error',
        results: [],
      };
    }
  }

  private getAuthHeaders(): HeadersInit {
    // Implement based on your auth setup
    return {
      Authorization: `Bearer ${this.getToken()}`,
      'Content-Type': 'application/json',
    };
  }

  private getToken(): string {
    // Implement based on your auth setup
    return '';
  }
}

interface SearchResult {
  status: 'success' | 'unavailable' | 'error';
  message?: string;
  results: Molecule[];
}

interface Molecule {
  id: string;
  smiles: string;
  inchi_key: string | null;
  name: string | null;
  molecular_weight: number | null;
  created_at: string;
  updated_at: string;
}
```

### Key Features

- **30-second cache**: Prevents excessive health check calls
- **5-second timeout**: Fast failure for unresponsive service
- **Structured responses**: Returns typed result instead of throwing
- **Cache clearing**: Allows manual retry to bypass cache

---

## Pattern 2: Service Status Badge Component

**File**: `apps/admin/components/compass/service-status.tsx`

### Implementation

```typescript
'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@repo/design-system/components/ui/badge';
import { RefreshCw } from 'lucide-react';

type ServiceStatus = 'checking' | 'online' | 'offline';

interface CompassServiceStatusProps {
  className?: string;
  showRetry?: boolean;
}

export function CompassServiceStatus({
  className,
  showRetry = true,
}: CompassServiceStatusProps) {
  const [status, setStatus] = useState<ServiceStatus>('checking');
  const [isRetrying, setIsRetrying] = useState(false);

  const checkStatus = async () => {
    try {
      const res = await fetch('/api/compass/health', {
        signal: AbortSignal.timeout(5000),
      });
      setStatus(res.ok ? 'online' : 'offline');
    } catch {
      setStatus('offline');
    }
  };

  const handleRetry = async () => {
    setIsRetrying(true);
    setStatus('checking');
    await checkStatus();
    setIsRetrying(false);
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 30000); // Poll every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const variants: Record<ServiceStatus, 'secondary' | 'default' | 'destructive'> = {
    checking: 'secondary',
    online: 'default',
    offline: 'destructive',
  };

  const labels: Record<ServiceStatus, string> = {
    checking: 'dk-data: checking...',
    online: 'dk-data: online',
    offline: 'dk-data: offline',
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Badge variant={variants[status]}>{labels[status]}</Badge>
      {showRetry && status === 'offline' && (
        <button
          onClick={handleRetry}
          disabled={isRetrying}
          className="p-1 hover:bg-gray-100 rounded"
          title="Retry connection"
        >
          <RefreshCw
            className={`h-4 w-4 ${isRetrying ? 'animate-spin' : ''}`}
          />
        </button>
      )}
    </div>
  );
}
```

### Usage in Compass Pages

```typescript
// apps/admin/app/(authenticated)/compass/search/page.tsx
import { CompassServiceStatus } from '@/components/compass/service-status';

export default function CompassSearchPage() {
  return (
    <div className="container mx-auto py-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Molecule Search</h1>
        <CompassServiceStatus />
      </div>
      {/* ... rest of page */}
    </div>
  );
}
```

### Key Features

- **Visual status indicator**: Clear badge showing service state
- **Auto-refresh**: Polls every 30 seconds
- **Manual retry**: Button to force immediate re-check
- **Loading state**: Shows "checking" during initial load

---

## Pattern 3: Health Proxy Endpoint

**File**: `apps/admin/app/api/compass/health/route.ts`

### Implementation

```typescript
import { NextResponse } from 'next/server';
import { env } from '@/env';

const DK_DATA_URL = env.DK_DATA_POSTGREST_URL || 'http://localhost:3030';
const TIMEOUT_MS = 5000;

export async function GET() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

    const response = await fetch(`${DK_DATA_URL}/health`, {
      method: 'GET',
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return NextResponse.json(
        {
          status: 'unhealthy',
          message: `dk-data returned ${response.status}`,
          timestamp: new Date().toISOString(),
        },
        { status: 503 }
      );
    }

    const data = await response.json();
    return NextResponse.json({
      status: 'healthy',
      upstream: data,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? error.name === 'AbortError'
          ? 'Connection timeout'
          : error.message
        : 'Unknown error';

    return NextResponse.json(
      {
        status: 'unavailable',
        message,
        timestamp: new Date().toISOString(),
      },
      { status: 503 }
    );
  }
}
```

### Key Features

- **Timeout handling**: 5-second timeout prevents hanging
- **Structured response**: Always returns JSON with status
- **Error categorization**: Distinguishes timeout from other errors
- **Timestamp**: Includes when check was performed

---

## Environment Configuration

**File**: `apps/admin/env.ts`

```typescript
import { createEnv } from '@t3-oss/env-nextjs';
import { z } from 'zod';

export const env = createEnv({
  server: {
    DK_DATA_POSTGREST_URL: z
      .string()
      .url()
      .default('http://localhost:3030'),
  },
  // ...
});
```

### Doppler Configuration

```bash
# Development
doppler secrets set DK_DATA_POSTGREST_URL="http://localhost:3030"

# Staging
doppler secrets set DK_DATA_POSTGREST_URL="https://dk-data-staging.behaviorlabs.ai"

# Production
doppler secrets set DK_DATA_POSTGREST_URL="https://dk-data.behaviorlabs.ai"
```

---

## Integration Testing

### Manual Test Procedure

1. **Service Online**:
   - Start dk-data locally: `docker-compose up -d`
   - Visit Compass search page
   - Verify badge shows "dk-data: online"
   - Perform search, verify results load

2. **Service Offline**:
   - Stop dk-data: `docker-compose down`
   - Visit Compass search page
   - Verify badge shows "dk-data: offline"
   - Attempt search, verify friendly error message
   - Click retry button, verify badge updates

3. **Service Recovery**:
   - With dk-data offline, observe "offline" badge
   - Restart dk-data
   - Wait up to 30 seconds or click retry
   - Verify badge updates to "online"

---

## Summary

| Pattern | Purpose | Cache TTL |
|---------|---------|-----------|
| Health Check Caching | Prevent excessive API calls | 30 seconds |
| Service Status Badge | Visual indicator for users | 30 seconds (polling) |
| Health Proxy Endpoint | Secure backend-to-backend call | None (pass-through) |

These patterns work together to provide:
- Clear service status visibility
- Graceful degradation during outages
- Automatic recovery detection
- Manual retry capability
