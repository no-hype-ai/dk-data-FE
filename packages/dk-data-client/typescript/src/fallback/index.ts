/**
 * Fallback modes for dk-data-client.
 *
 *   strict    — raise DkDataNotFoundError / DkDataStaleError immediately
 *   upstream  — try the upstream source (PubChem, CT.gov, Europe PMC…),
 *               transform the response to match dk-data shape, NO
 *               write-back in v0.1
 *   hydrate   — v1.1 — same as upstream + write-back (idempotent
 *               ingestion endpoints required; currently throws)
 */

import {
  DkDataNotFoundError,
  DkDataUpstreamError,
} from "../errors.js";

export type FallbackMode = "strict" | "upstream" | "hydrate";

export interface FallbackContext {
  method: string;
  args: Record<string, unknown>;
  upstreamName: string;
}

export interface UpstreamShim {
  readonly upstreamName: string;
  fetch(ctx: FallbackContext): Promise<unknown>;
}

// -----------------------------------------------------------------------------
// v0.1 shims
// -----------------------------------------------------------------------------

export class PubchemMoleculeShim implements UpstreamShim {
  readonly upstreamName = "pubchem";

  async fetch(ctx: FallbackContext): Promise<unknown> {
    const nameOrId = (ctx.args.name_or_id ?? ctx.args.id) as string | undefined;
    if (!nameOrId) {
      throw new DkDataNotFoundError(`no identifier for ${ctx.method}`);
    }
    const url =
      `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/` +
      `${encodeURIComponent(nameOrId)}/property/InChIKey,CanonicalSMILES,MolecularFormula/JSON`;
    let resp: Response;
    try {
      resp = await fetch(url);
    } catch (e) {
      throw new DkDataUpstreamError(`pubchem fetch failed: ${String(e)}`, {
        upstream: this.upstreamName,
      });
    }
    if (resp.status === 404) {
      throw new DkDataNotFoundError(`not found in pubchem: ${nameOrId}`);
    }
    if (resp.status >= 500) {
      throw new DkDataUpstreamError(`pubchem returned ${resp.status}`, {
        upstream: this.upstreamName,
      });
    }
    const data = (await resp.json()) as {
      PropertyTable?: { Properties?: Array<Record<string, unknown>> };
    };
    const props = data.PropertyTable?.Properties ?? [];
    if (props.length === 0) {
      throw new DkDataNotFoundError(`pubchem returned empty: ${nameOrId}`);
    }
    const row = props[0]!;
    return [
      {
        id: `PUBCHEM:${row.CID as string | undefined}`,
        inchi_key: row.InChIKey,
        canonical_smiles: row.CanonicalSMILES,
        molecular_formula: row.MolecularFormula,
        source: "pubchem",
        fallthrough: true,
      },
    ];
  }
}

export class ClinicalTrialsShim implements UpstreamShim {
  readonly upstreamName = "clinicaltrials.gov";

  async fetch(ctx: FallbackContext): Promise<unknown> {
    const query = (ctx.args.id ?? ctx.args.name_or_id) as string | undefined;
    if (!query) {
      throw new DkDataNotFoundError(`no query for ${ctx.method}`);
    }
    const url = new URL("https://clinicaltrials.gov/api/v2/studies");
    url.searchParams.set("query.term", query);
    url.searchParams.set("pageSize", "50");
    url.searchParams.set("format", "json");
    let resp: Response;
    try {
      resp = await fetch(url.toString());
    } catch (e) {
      throw new DkDataUpstreamError(`ct.gov fetch failed: ${String(e)}`, {
        upstream: this.upstreamName,
      });
    }
    if (resp.status >= 500) {
      throw new DkDataUpstreamError(`ct.gov returned ${resp.status}`, {
        upstream: this.upstreamName,
      });
    }
    interface StudyShape {
      protocolSection?: {
        identificationModule?: {
          nctId?: string;
          briefTitle?: string;
        };
      };
    }
    const data = (await resp.json()) as { studies?: StudyShape[] };
    const studies = data.studies ?? [];
    return studies.map((s) => ({
      nct_id: s.protocolSection?.identificationModule?.nctId,
      title: s.protocolSection?.identificationModule?.briefTitle,
      source: "ct.gov",
      fallthrough: true,
    }));
  }
}

export class EuropePMCShim implements UpstreamShim {
  readonly upstreamName = "europe-pmc";

  async fetch(ctx: FallbackContext): Promise<unknown> {
    const query = ctx.args.query as string | undefined;
    if (!query) {
      throw new DkDataNotFoundError(`no query for ${ctx.method}`);
    }
    const url = new URL("https://www.ebi.ac.uk/europepmc/webservices/rest/search");
    url.searchParams.set("query", query);
    url.searchParams.set("format", "json");
    url.searchParams.set("pageSize", "25");
    let resp: Response;
    try {
      resp = await fetch(url.toString());
    } catch (e) {
      throw new DkDataUpstreamError(`europe-pmc fetch failed: ${String(e)}`, {
        upstream: this.upstreamName,
      });
    }
    if (resp.status >= 500) {
      throw new DkDataUpstreamError(`europe-pmc returned ${resp.status}`, {
        upstream: this.upstreamName,
      });
    }
    interface HitShape {
      id?: string;
      title?: string;
      doi?: string;
    }
    const data = (await resp.json()) as { resultList?: { result?: HitShape[] } };
    const hits = data.resultList?.result ?? [];
    return hits.map((h) => ({
      id: h.id,
      title: h.title,
      doi: h.doi,
      source: "europe-pmc",
      fallthrough: true,
    }));
  }
}

const _registry = new Map<string, UpstreamShim>([
  ["molecules.resolve", new PubchemMoleculeShim()],
  ["molecules.get", new PubchemMoleculeShim()],
  ["molecules.getClinicalTrials", new ClinicalTrialsShim()],
  ["publications.search", new EuropePMCShim()],
]);

export function registerShim(method: string, shim: UpstreamShim): void {
  _registry.set(method, shim);
}

export function getShim(method: string): UpstreamShim | undefined {
  return _registry.get(method);
}

export function clearShims(): void {
  _registry.clear();
}

export async function fallbackToUpstream(
  method: string,
  args: Record<string, unknown>,
  mode: FallbackMode,
): Promise<{ value: unknown; upstreamName: string }> {
  if (mode === "strict") {
    throw new DkDataNotFoundError(`strict fallback: ${method}`);
  }
  if (mode === "hydrate") {
    throw new Error(
      "hydrate fallback is scheduled for v1.1 (idempotent ingestion required)",
    );
  }
  const shim = _registry.get(method);
  if (!shim) {
    throw new DkDataNotFoundError(
      `no upstream shim registered for ${method}; cannot fallback`,
    );
  }
  const ctx: FallbackContext = {
    method,
    args,
    upstreamName: shim.upstreamName,
  };
  const value = await shim.fetch(ctx);
  return { value, upstreamName: shim.upstreamName };
}
