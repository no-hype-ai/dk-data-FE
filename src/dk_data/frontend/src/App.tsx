/**
 * DK Data Platform - Data Source Onboarding
 *
 * Standalone UI for onboarding new data sources to the DK Data Platform:
 * - 5-step wizard for data source configuration
 * - Schema detection and entity linking setup
 * - Database table generation
 */

import React, { useState } from 'react';
import {
  Play,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ExternalLink,
  Database,
  Activity,
  Settings,
  ChevronRight,
  Loader,
  Plus,
  Key,
  FileJson,
  Table,
  Zap,
  X,
  Check,
  Network,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const GRAFANA_URL = 'http://localhost:3003';

// Identifier types for entity linking
const IDENTIFIER_TYPES = [
  { value: 'none', label: 'No Entity Linking', description: 'Do not link to molecules' },
  { value: 'inchikey', label: 'InChIKey', description: 'Standard InChIKey identifier (27 chars)' },
  { value: 'smiles', label: 'SMILES', description: 'SMILES structure notation' },
  { value: 'cas', label: 'CAS Number', description: 'CAS Registry Number (e.g., 50-78-2)' },
  { value: 'chembl_id', label: 'ChEMBL ID', description: 'ChEMBL compound ID (e.g., CHEMBL25)' },
  { value: 'pubchem_cid', label: 'PubChem CID', description: 'PubChem Compound ID' },
  { value: 'drugbank_id', label: 'DrugBank ID', description: 'DrugBank accession (e.g., DB00945)' },
  { value: 'drug_name', label: 'Drug Name', description: 'Drug/molecule name (fuzzy matching)' },
  { value: 'unii', label: 'UNII', description: 'FDA Unique Ingredient Identifier' },
];

// Pagination types
const PAGINATION_TYPES = [
  { value: 'none', label: 'No Pagination', description: 'Single request, all data at once' },
  { value: 'offset', label: 'Offset/Limit', description: 'Uses offset=N&limit=M parameters' },
  { value: 'page', label: 'Page Number', description: 'Uses page=N&page_size=M parameters' },
  { value: 'cursor', label: 'Cursor-based', description: 'Uses cursor token for next page' },
  { value: 'next_url', label: 'Next URL', description: 'Response contains URL to next page' },
];

// Incremental sync types
const INCREMENTAL_TYPES = [
  { value: 'none', label: 'Full Sync (with dedup)', description: 'Always fetch all data, deduplicate by hash' },
  { value: 'modified_since', label: 'Modified Since', description: 'Only fetch records modified since last sync' },
  { value: 'created_since', label: 'Created Since', description: 'Only fetch newly created records' },
  { value: 'offset_resume', label: 'Resume from Offset', description: 'Continue from last position (for append-only APIs)' },
];

// Date format options for incremental sync
const DATE_FORMATS = [
  { value: '%Y-%m-%dT%H:%M:%SZ', label: 'ISO 8601', example: '2024-01-26T10:30:00Z' },
  { value: '%Y%m%d', label: 'YYYYMMDD', example: '20240126 (FDA style)' },
  { value: '%Y-%m-%d', label: 'YYYY-MM-DD', example: '2024-01-26' },
  { value: '%s', label: 'Unix Timestamp', example: '1706259000' },
];

// Onboarding wizard types
interface OnboardingData {
  source_id: string;
  source_name: string;
  api_type: 'REST' | 'GraphQL' | 'FILE' | 'DATABASE';
  base_url: string;
  auth_type: 'NONE' | 'API_KEY' | 'OAUTH2' | 'BASIC' | 'BEARER';
  refresh_tier: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'on_demand';
  rate_limit_per_second: number;
  description: string;
  credential_key?: string;
  credential_value?: string;
  http_method?: 'GET' | 'POST';
  custom_headers?: string;
  query_params?: string;
  data_path?: string;
  pagination_type?: string;
  page_size?: number;
  incremental_type?: string;
  date_field?: string;
  date_param?: string;
  date_format?: string;
  lookback_hours?: number;
  sample_response?: string;
  identifier_field?: string;
  identifier_type?: string;
  secondary_identifier_field?: string;
  secondary_identifier_type?: string;
}

interface TestConnectionResult {
  success: boolean;
  status_code: number;
  response_time_ms: number;
  sample_data: unknown[] | null;
  record_count: number;
  detected_fields: unknown[];
  error: string | null;
}

interface DetectedColumn {
  name: string;
  type: string;
  nullable?: boolean;
}

interface DetectedSchema {
  columns: DetectedColumn[];
  table_name?: string;
}

const ONBOARDING_STEPS = [
  { id: 1, name: 'Source Info', description: 'Basic source configuration', icon: Database },
  { id: 2, name: 'Authentication', description: 'Set up credentials', icon: Key },
  { id: 3, name: 'Schema Detection', description: 'Detect data structure', icon: FileJson },
  { id: 4, name: 'Generate Table', description: 'Create database table', icon: Table },
  { id: 5, name: 'Complete', description: 'Ready to sync', icon: Zap },
];

function App() {
  const [error, setError] = useState<string | null>(null);
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [onboardingData, setOnboardingData] = useState<OnboardingData>({
    source_id: '',
    source_name: '',
    api_type: 'REST',
    base_url: '',
    auth_type: 'NONE',
    refresh_tier: 'weekly',
    rate_limit_per_second: 10,
    description: '',
  });
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [onboardingResult, setOnboardingResult] = useState<{ ddl?: string } | null>(null);
  const [detectedSchema, setDetectedSchema] = useState<DetectedSchema | null>(null);
  const [testConnectionResult, setTestConnectionResult] = useState<TestConnectionResult | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);

  // Test API connection and auto-fetch sample
  const handleTestConnection = async () => {
    if (!onboardingData.base_url) {
      setError('Please enter a URL first');
      return;
    }

    setTestingConnection(true);
    setError(null);
    setTestConnectionResult(null);

    try {
      let headers: Record<string, string> = {};
      if (onboardingData.custom_headers) {
        try {
          headers = JSON.parse(onboardingData.custom_headers);
        } catch {
          onboardingData.custom_headers.split('\n').forEach(line => {
            const [key, ...valueParts] = line.split(':');
            if (key && valueParts.length) {
              headers[key.trim()] = valueParts.join(':').trim();
            }
          });
        }
      }

      let queryParams: Record<string, string> = {};
      if (onboardingData.query_params) {
        try {
          queryParams = JSON.parse(onboardingData.query_params);
        } catch {
          onboardingData.query_params.split('\n').forEach(line => {
            const [key, ...valueParts] = line.split('=');
            if (key && valueParts.length) {
              queryParams[key.trim()] = valueParts.join('=').trim();
            }
          });
        }
      }

      const res = await fetch(`${API_BASE}/api/v1/data-sources/test-connection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: onboardingData.base_url,
          method: onboardingData.http_method || 'GET',
          headers,
          query_params: queryParams,
          auth_type: onboardingData.auth_type.toLowerCase(),
          auth_value: onboardingData.credential_value,
          auth_header: onboardingData.credential_key || 'Authorization',
          data_path: onboardingData.data_path,
          timeout_seconds: 30,
        }),
      });

      const result = await res.json();
      setTestConnectionResult(result);

      if (result.success && result.sample_data) {
        setOnboardingData(prev => ({
          ...prev,
          sample_response: JSON.stringify(result.sample_data[0], null, 2),
        }));
      }
    } catch (e) {
      setTestConnectionResult({
        success: false,
        status_code: 0,
        response_time_ms: 0,
        sample_data: null,
        record_count: 0,
        detected_fields: [],
        error: e instanceof Error ? e.message : 'Connection test failed',
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleOnboardingNext = async () => {
    if (onboardingStep < 5) {
      if (onboardingStep === 1) {
        setOnboardingLoading(true);
        try {
          const requestConfig = (onboardingData.http_method || onboardingData.data_path || onboardingData.custom_headers) ? {
            method: onboardingData.http_method || 'GET',
            data_path: onboardingData.data_path || null,
            headers: onboardingData.custom_headers ? (() => {
              try { return JSON.parse(onboardingData.custom_headers); }
              catch { return {}; }
            })() : {},
            query_params: onboardingData.query_params ? (() => {
              try { return JSON.parse(onboardingData.query_params); }
              catch { return {}; }
            })() : {},
          } : undefined;

          const paginationConfig = onboardingData.pagination_type && onboardingData.pagination_type !== 'none' ? {
            type: onboardingData.pagination_type,
            page_size: onboardingData.page_size || 100,
            max_pages: 100,
          } : undefined;

          const incrementalConfig = onboardingData.incremental_type && onboardingData.incremental_type !== 'none' ? {
            type: onboardingData.incremental_type,
            date_field: onboardingData.date_field || null,
            date_param: onboardingData.date_param || null,
            date_format: onboardingData.date_format || '%Y-%m-%dT%H:%M:%SZ',
            lookback_hours: onboardingData.lookback_hours || 168,
          } : undefined;

          const res = await fetch(`${API_BASE}/api/v1/data-sources/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: onboardingData.source_id,
              display_name: onboardingData.source_name,
              api_type: onboardingData.api_type.toLowerCase(),
              base_url: onboardingData.base_url,
              auth_type: onboardingData.auth_type.toLowerCase(),
              refresh_tier: onboardingData.refresh_tier,
              rate_limit_requests: onboardingData.rate_limit_per_second,
              description: onboardingData.description,
              request_config: requestConfig,
              pagination_config: paginationConfig,
              incremental_config: incrementalConfig,
            }),
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Failed to register source');
          }
          setOnboardingResult(await res.json());
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to register data source');
          setOnboardingLoading(false);
          return;
        }
        setOnboardingLoading(false);
      }

      if (onboardingStep === 2 && onboardingData.auth_type !== 'NONE' && onboardingData.credential_value) {
        setOnboardingLoading(true);
        try {
          const res = await fetch(
            `${API_BASE}/api/v1/data-sources/${onboardingData.source_id}/credentials`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                key_name: onboardingData.credential_key || 'api_key',
                value: onboardingData.credential_value,
              }),
            }
          );
          if (!res.ok) throw new Error('Failed to store credentials');
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to store credentials');
          setOnboardingLoading(false);
          return;
        }
        setOnboardingLoading(false);
      }

      if (onboardingStep === 3 && onboardingData.sample_response) {
        setOnboardingLoading(true);
        try {
          const res = await fetch(
            `${API_BASE}/api/v1/data-sources/${onboardingData.source_id}/detect-schema`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                sample_responses: [JSON.parse(onboardingData.sample_response)],
              }),
            }
          );
          if (!res.ok) throw new Error('Failed to detect schema');
          const schema = await res.json();
          setDetectedSchema(schema);
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to detect schema. Ensure JSON is valid.');
          setOnboardingLoading(false);
          return;
        }
        setOnboardingLoading(false);
      }

      if (onboardingStep === 4 && detectedSchema) {
        setOnboardingLoading(true);
        try {
          const res = await fetch(
            `${API_BASE}/api/v1/data-sources/${onboardingData.source_id}/generate-table`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                fields: detectedSchema.columns,
                table_name: detectedSchema.table_name,
                entity_linking: {
                  identifier_field: onboardingData.identifier_field || null,
                  identifier_type: onboardingData.identifier_type !== 'none' ? onboardingData.identifier_type : null,
                  secondary_identifier_field: onboardingData.secondary_identifier_field || null,
                  secondary_identifier_type: onboardingData.secondary_identifier_type !== 'none' ? onboardingData.secondary_identifier_type : null,
                },
              }),
            }
          );
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Failed to generate table');
          }
          setOnboardingResult(await res.json());
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to generate table');
          setOnboardingLoading(false);
          return;
        }
        setOnboardingLoading(false);
      }

      setOnboardingStep(onboardingStep + 1);
    }
  };

  const resetOnboarding = () => {
    setOnboardingStep(1);
    setOnboardingData({
      source_id: '',
      source_name: '',
      api_type: 'REST',
      base_url: '',
      auth_type: 'NONE',
      refresh_tier: 'weekly',
      rate_limit_per_second: 10,
      description: '',
    });
    setOnboardingResult(null);
    setDetectedSchema(null);
    setTestConnectionResult(null);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">DK Data Platform</h1>
              <p className="mt-1 text-sm text-gray-600">
                Data Source Onboarding
              </p>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={GRAFANA_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary flex items-center gap-2 text-sm"
              >
                <Activity className="w-4 h-4" />
                Grafana
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Stepper */}
        <div className="card p-4 mb-6">
          <div className="flex items-center justify-between">
            {ONBOARDING_STEPS.map((step, idx) => (
              <React.Fragment key={step.id}>
                <div
                  className={`flex items-center gap-2 ${
                    step.id <= onboardingStep ? 'text-primary-600' : 'text-gray-400'
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                      step.id < onboardingStep
                        ? 'bg-primary-600 text-white'
                        : step.id === onboardingStep
                        ? 'bg-primary-100 text-primary-700 border-2 border-primary-600'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {step.id < onboardingStep ? <Check className="w-4 h-4" /> : step.id}
                  </div>
                  <div className="hidden sm:block">
                    <div className="text-sm font-medium">{step.name}</div>
                    <div className="text-xs text-gray-500">{step.description}</div>
                  </div>
                </div>
                {idx < ONBOARDING_STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mx-2 ${
                      step.id < onboardingStep ? 'bg-primary-600' : 'bg-gray-200'
                    }`}
                  />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <div className="card p-6">
          {/* Step 1: Source Info */}
          {onboardingStep === 1 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Configure Data Source</h3>
              <p className="text-sm text-gray-600">
                Enter the basic information about your new data source.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Source ID *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g., my_custom_api"
                    value={onboardingData.source_id}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, source_id: e.target.value.toLowerCase().replace(/\s+/g, '_') })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Unique identifier (lowercase, no spaces)</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Display Name *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g., My Custom Drug API"
                    value={onboardingData.source_name}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, source_name: e.target.value })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API Type</label>
                  <select
                    value={onboardingData.api_type}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, api_type: e.target.value as OnboardingData['api_type'] })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="REST">REST API</option>
                    <option value="GraphQL">GraphQL</option>
                    <option value="FILE">File (CSV/JSON)</option>
                    <option value="DATABASE">Database</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
                  <input
                    type="url"
                    placeholder="https://api.example.com/v1"
                    value={onboardingData.base_url}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, base_url: e.target.value })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Authentication
                  </label>
                  <select
                    value={onboardingData.auth_type}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, auth_type: e.target.value as OnboardingData['auth_type'] })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="NONE">No Authentication</option>
                    <option value="API_KEY">API Key</option>
                    <option value="BEARER">Bearer Token</option>
                    <option value="BASIC">Basic Auth</option>
                    <option value="OAUTH2">OAuth2</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Refresh Frequency
                  </label>
                  <select
                    value={onboardingData.refresh_tier}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, refresh_tier: e.target.value as OnboardingData['refresh_tier'] })
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="on_demand">On Demand</option>
                  </select>
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    placeholder="Brief description of the data source..."
                    value={onboardingData.description}
                    onChange={(e) =>
                      setOnboardingData({ ...onboardingData, description: e.target.value })
                    }
                    rows={2}
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              {/* Test Connection Button */}
              {onboardingData.base_url && (
                <div className="mt-6 p-4 bg-gray-50 rounded-lg border">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Test Connection</h4>
                      <p className="text-xs text-gray-500">
                        Verify the API is accessible and auto-detect schema
                      </p>
                    </div>
                    <button
                      onClick={handleTestConnection}
                      disabled={testingConnection}
                      className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center space-x-2"
                    >
                      {testingConnection ? (
                        <>
                          <Loader className="w-4 h-4 animate-spin" />
                          <span>Testing...</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-4 h-4" />
                          <span>Test Connection</span>
                        </>
                      )}
                    </button>
                  </div>

                  {testConnectionResult && (
                    <div className={`mt-3 p-3 rounded-lg ${
                      testConnectionResult.success
                        ? 'bg-green-50 border border-green-200'
                        : 'bg-red-50 border border-red-200'
                    }`}>
                      <div className="flex items-center space-x-2">
                        {testConnectionResult.success ? (
                          <CheckCircle className="w-5 h-5 text-green-500" />
                        ) : (
                          <XCircle className="w-5 h-5 text-red-500" />
                        )}
                        <span className={`text-sm font-medium ${
                          testConnectionResult.success ? 'text-green-700' : 'text-red-700'
                        }`}>
                          {testConnectionResult.success
                            ? `Success! Found ${testConnectionResult.record_count} records in ${testConnectionResult.response_time_ms.toFixed(0)}ms`
                            : testConnectionResult.error}
                        </span>
                      </div>
                      {testConnectionResult.success && testConnectionResult.detected_fields.length > 0 && (
                        <div className="mt-2 text-xs text-green-600">
                          Detected {testConnectionResult.detected_fields.length} fields. Sample data has been auto-loaded for schema detection.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Advanced Configuration */}
              <details className="mt-6">
                <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-primary-600">
                  <Settings className="w-4 h-4 inline mr-2" />
                  Advanced Configuration
                </summary>
                <div className="mt-4 space-y-4 pl-4 border-l-2 border-gray-200">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        HTTP Method
                      </label>
                      <select
                        value={onboardingData.http_method || 'GET'}
                        onChange={(e) =>
                          setOnboardingData({ ...onboardingData, http_method: e.target.value as OnboardingData['http_method'] })
                        }
                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Data Path
                      </label>
                      <input
                        type="text"
                        placeholder="e.g., results or data.items"
                        value={onboardingData.data_path || ''}
                        onChange={(e) =>
                          setOnboardingData({ ...onboardingData, data_path: e.target.value })
                        }
                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        JSON path to data array (if not at root)
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Pagination Type
                      </label>
                      <select
                        value={onboardingData.pagination_type || 'none'}
                        onChange={(e) =>
                          setOnboardingData({ ...onboardingData, pagination_type: e.target.value })
                        }
                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      >
                        {PAGINATION_TYPES.map((pt) => (
                          <option key={pt.value} value={pt.value}>
                            {pt.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-gray-500 mt-1">
                        {PAGINATION_TYPES.find(p => p.value === (onboardingData.pagination_type || 'none'))?.description}
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Page Size
                      </label>
                      <input
                        type="number"
                        placeholder="100"
                        value={onboardingData.page_size || 100}
                        onChange={(e) =>
                          setOnboardingData({ ...onboardingData, page_size: parseInt(e.target.value) || 100 })
                        }
                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Sync Mode
                        </label>
                        <select
                          value={onboardingData.incremental_type || 'none'}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, incremental_type: e.target.value })
                          }
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                          {INCREMENTAL_TYPES.map((it) => (
                            <option key={it.value} value={it.value}>
                              {it.label}
                            </option>
                          ))}
                        </select>
                        <p className="text-xs text-gray-500 mt-1">
                          {INCREMENTAL_TYPES.find(i => i.value === (onboardingData.incremental_type || 'none'))?.description}
                        </p>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Lookback Period (hours)
                        </label>
                        <input
                          type="number"
                          placeholder="168"
                          value={onboardingData.lookback_hours || 168}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, lookback_hours: parseInt(e.target.value) || 168 })
                          }
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          How far back to re-check for updates (168 = 1 week)
                        </p>
                      </div>
                    </div>

                    {onboardingData.incremental_type && onboardingData.incremental_type !== 'none' && onboardingData.incremental_type !== 'offset_resume' && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Date Field in Response
                          </label>
                          <input
                            type="text"
                            placeholder="e.g., effective_time, modified_at"
                            value={onboardingData.date_field || ''}
                            onChange={(e) =>
                              setOnboardingData({ ...onboardingData, date_field: e.target.value })
                            }
                            className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            API Date Parameter
                          </label>
                          <input
                            type="text"
                            placeholder="e.g., since, search"
                            value={onboardingData.date_param || ''}
                            onChange={(e) =>
                              setOnboardingData({ ...onboardingData, date_param: e.target.value })
                            }
                            className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Date Format
                          </label>
                          <select
                            value={onboardingData.date_format || '%Y-%m-%dT%H:%M:%SZ'}
                            onChange={(e) =>
                              setOnboardingData({ ...onboardingData, date_format: e.target.value })
                            }
                            className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                          >
                            {DATE_FORMATS.map((df) => (
                              <option key={df.value} value={df.value}>
                                {df.label} ({df.example})
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Custom Headers (JSON or key: value per line)
                    </label>
                    <textarea
                      placeholder={'{"X-Custom-Header": "value"}\nor\nX-Custom-Header: value'}
                      value={onboardingData.custom_headers || ''}
                      onChange={(e) =>
                        setOnboardingData({ ...onboardingData, custom_headers: e.target.value })
                      }
                      rows={2}
                      className="w-full px-3 py-2 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>
              </details>
            </div>
          )}

          {/* Step 2: Authentication */}
          {onboardingStep === 2 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Configure Authentication</h3>
              <p className="text-sm text-gray-600">
                {onboardingData.auth_type === 'NONE'
                  ? 'No authentication required. You can skip to the next step.'
                  : 'Enter your API credentials. They will be encrypted before storage.'}
              </p>

              {onboardingData.auth_type !== 'NONE' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Credential Name
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., api_key"
                      value={onboardingData.credential_key || ''}
                      onChange={(e) =>
                        setOnboardingData({ ...onboardingData, credential_key: e.target.value })
                      }
                      className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Credential Value
                    </label>
                    <input
                      type="password"
                      placeholder="Enter your API key or token"
                      value={onboardingData.credential_value || ''}
                      onChange={(e) =>
                        setOnboardingData({ ...onboardingData, credential_value: e.target.value })
                      }
                      className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>
              )}

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
                <strong>Security Note:</strong> Credentials are encrypted with AES-256-GCM before storage.
              </div>
            </div>
          )}

          {/* Step 3: Schema Detection */}
          {onboardingStep === 3 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Detect Schema</h3>
              <p className="text-sm text-gray-600">
                Paste a sample API response to auto-detect the data schema.
              </p>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Sample API Response (JSON)
                </label>
                <textarea
                  placeholder='{"id": "12345", "name": "Aspirin", "formula": "C9H8O4", ...}'
                  value={onboardingData.sample_response || ''}
                  onChange={(e) =>
                    setOnboardingData({ ...onboardingData, sample_response: e.target.value })
                  }
                  rows={8}
                  className="w-full px-3 py-2 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {detectedSchema && (
                <div className="space-y-4">
                  <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                    <h4 className="font-medium text-green-800 mb-2 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      Schema Detected
                    </h4>
                    <div className="text-sm text-green-700">
                      {detectedSchema.columns?.length || 0} columns detected
                    </div>
                    <pre className="mt-2 text-xs bg-white p-2 rounded overflow-x-auto max-h-40">
                      {JSON.stringify(detectedSchema.columns?.slice(0, 10), null, 2)}
                    </pre>
                  </div>

                  {/* Entity Linking Configuration */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
                      <Network className="w-4 h-4" />
                      Entity Linking Configuration
                    </h4>
                    <p className="text-sm text-blue-700 mb-4">
                      Configure how records from this source should be linked to the master molecule database.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Primary Identifier Field
                        </label>
                        <select
                          value={onboardingData.identifier_field || ''}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, identifier_field: e.target.value })
                          }
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                          <option value="">-- Select field --</option>
                          {detectedSchema.columns?.map((col: DetectedColumn) => (
                            <option key={col.name} value={col.name}>
                              {col.name} ({col.type})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Identifier Type
                        </label>
                        <select
                          value={onboardingData.identifier_type || 'none'}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, identifier_type: e.target.value })
                          }
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                          {IDENTIFIER_TYPES.map((type) => (
                            <option key={type.value} value={type.value}>
                              {type.label}
                            </option>
                          ))}
                        </select>
                        <p className="text-xs text-gray-500 mt-1">
                          {IDENTIFIER_TYPES.find(t => t.value === (onboardingData.identifier_type || 'none'))?.description}
                        </p>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Secondary Identifier Field <span className="text-gray-400">(optional)</span>
                        </label>
                        <select
                          value={onboardingData.secondary_identifier_field || ''}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, secondary_identifier_field: e.target.value })
                          }
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                          <option value="">-- None --</option>
                          {detectedSchema.columns?.map((col: DetectedColumn) => (
                            <option key={col.name} value={col.name}>
                              {col.name} ({col.type})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Secondary Identifier Type
                        </label>
                        <select
                          value={onboardingData.secondary_identifier_type || 'none'}
                          onChange={(e) =>
                            setOnboardingData({ ...onboardingData, secondary_identifier_type: e.target.value })
                          }
                          disabled={!onboardingData.secondary_identifier_field}
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-100"
                        >
                          {IDENTIFIER_TYPES.map((type) => (
                            <option key={type.value} value={type.value}>
                              {type.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {onboardingData.identifier_type && onboardingData.identifier_type !== 'none' && (
                      <div className="mt-3 p-2 bg-blue-100 rounded text-sm text-blue-800">
                        Records will be linked using <strong>{onboardingData.identifier_field}</strong> as{' '}
                        <strong>{IDENTIFIER_TYPES.find(t => t.value === onboardingData.identifier_type)?.label}</strong>
                        {onboardingData.secondary_identifier_field && (
                          <>, with fallback to <strong>{onboardingData.secondary_identifier_field}</strong></>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 4: Generate Table */}
          {onboardingStep === 4 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Generate Database Table</h3>
              <p className="text-sm text-gray-600">
                Review the detected schema and generate the database table.
              </p>

              {detectedSchema && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <h4 className="font-medium mb-2">Table: raw.{onboardingData.source_id}</h4>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-2">Column</th>
                          <th className="text-left py-2 px-2">Type</th>
                          <th className="text-left py-2 px-2">Nullable</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detectedSchema.columns?.slice(0, 15).map((col: DetectedColumn, idx: number) => (
                          <tr key={idx} className="border-b">
                            <td className="py-1.5 px-2 font-mono">{col.name}</td>
                            <td className="py-1.5 px-2">{col.type}</td>
                            <td className="py-1.5 px-2">{col.nullable ? 'Yes' : 'No'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {onboardingResult?.ddl && (
                <div className="bg-gray-900 rounded-lg p-4 text-green-400 font-mono text-xs overflow-x-auto">
                  <pre>{onboardingResult.ddl}</pre>
                </div>
              )}
            </div>
          )}

          {/* Step 5: Complete */}
          {onboardingStep === 5 && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Onboarding Complete!</h3>
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-8 h-8 text-green-600" />
                  <div>
                    <h4 className="font-medium text-green-800">
                      Data source "{onboardingData.source_name}" has been configured
                    </h4>
                    <p className="text-sm text-green-700">
                      The source is now ready for data ingestion.
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="font-medium mb-3">Next Steps</h4>
                <ul className="space-y-2 text-sm">
                  <li className="flex items-center gap-2">
                    <ChevronRight className="w-4 h-4 text-primary-600" />
                    Trigger a manual sync using the API or job scheduler
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="w-4 h-4 text-primary-600" />
                    Monitor the job in Grafana dashboards
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="w-4 h-4 text-primary-600" />
                    Configure Bronze/Silver transformations for entity resolution
                  </li>
                </ul>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={resetOnboarding}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Onboard Another Source
                </button>
                <a
                  href={GRAFANA_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary flex items-center gap-2"
                >
                  <Activity className="w-4 h-4" />
                  Open Grafana
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          )}

          {/* Navigation Buttons */}
          {onboardingStep < 5 && (
            <div className="flex justify-between mt-6 pt-4 border-t">
              <button
                onClick={() => setOnboardingStep(Math.max(1, onboardingStep - 1))}
                disabled={onboardingStep === 1}
                className="btn btn-secondary text-sm disabled:opacity-50"
              >
                Back
              </button>
              <button
                onClick={handleOnboardingNext}
                disabled={
                  onboardingLoading ||
                  (onboardingStep === 1 && (!onboardingData.source_id || !onboardingData.source_name))
                }
                className="btn btn-primary text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {onboardingLoading ? (
                  <>
                    <Loader className="w-4 h-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    {onboardingStep === 4 ? 'Create Table' : 'Continue'}
                    <ChevronRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
