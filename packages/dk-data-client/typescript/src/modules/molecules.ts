/**
 * Molecule read surface — mirrors `dk_data_client.modules.molecules`.
 */

import { ModuleBase } from "./_base.js";

export interface MoleculeRef {
  molecule_id: string;
  canonical_name?: string;
  inchi_key?: string;
}

export interface Molecule extends MoleculeRef {
  [key: string]: unknown;
}

export class MoleculesModule extends ModuleBase {
  async resolve(nameOrId: string, opts: { hint?: string } = {}): Promise<MoleculeRef> {
    const body: Record<string, unknown> = { name_or_id: nameOrId };
    if (opts.hint) body.hint = opts.hint;
    return (await this.call({
      method: "molecules.resolve",
      path: "/data-platform/molecules/resolve",
      args: { nameOrId, hint: opts.hint },
      httpMethod: "POST",
      jsonBody: body,
    })) as MoleculeRef;
  }

  async search(query: string, opts: { limit?: number } = {}): Promise<Molecule[]> {
    const data = (await this.call({
      method: "molecules.search",
      path: "/molecules",
      args: { query, limit: opts.limit ?? 25 },
      params: {
        select: "molecule_id,canonical_name,inchi_key",
        or: `(canonical_name.ilike.*${query}*,molecule_id.eq.${query})`,
        limit: String(opts.limit ?? 25),
      },
    })) as Molecule[];
    return Array.isArray(data) ? data : [];
  }

  async get(moleculeId: string): Promise<Molecule> {
    const rows = (await this.call({
      method: "molecules.get",
      path: "/molecules",
      args: { id: moleculeId },
      params: { molecule_id: `eq.${moleculeId}`, limit: "1" },
    })) as Molecule[];
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : ({} as Molecule);
  }

  async getProfile(moleculeId: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "molecules.getProfile",
      path: "/molecule_profile",
      args: { id: moleculeId },
      params: { molecule_id: `eq.${moleculeId}`, limit: "1" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }

  async getSafety(moleculeId: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "molecules.getSafety",
      path: "/safety_signals",
      args: { id: moleculeId },
      params: { molecule_id: `eq.${moleculeId}` },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }

  async getAdverseEvents(
    moleculeId: string,
    opts: { limit?: number } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "molecules.getAdverseEvents",
      path: "/adverse_events",
      args: { id: moleculeId, limit: opts.limit ?? 100 },
      params: { molecule_id: `eq.${moleculeId}`, limit: String(opts.limit ?? 100) },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getClinicalTrials(
    moleculeId: string,
    opts: { phase?: string; limit?: number } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const params: Record<string, string> = {
      molecule_id: `eq.${moleculeId}`,
      limit: String(opts.limit ?? 100),
    };
    if (opts.phase) params.phase = `eq.${opts.phase}`;
    const data = (await this.call({
      method: "molecules.getClinicalTrials",
      path: "/clinical_trials",
      args: { id: moleculeId, phase: opts.phase, limit: opts.limit ?? 100 },
      params,
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getDrugLabels(moleculeId: string): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "molecules.getDrugLabels",
      path: "/drug_labels",
      args: { id: moleculeId },
      params: { molecule_id: `eq.${moleculeId}` },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getBoxedWarnings(moleculeId: string): Promise<Array<Record<string, unknown>>> {
    // Inline column on mol_silver.drug_labels — see feature 002 scope note.
    const data = (await this.call({
      method: "molecules.getBoxedWarnings",
      path: "/drug_labels",
      args: { id: moleculeId },
      params: {
        molecule_id: `eq.${moleculeId}`,
        boxed_warning: "not.is.null",
        select: "molecule_id,boxed_warning,label_date",
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getContraindications(
    moleculeId: string,
  ): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "molecules.getContraindications",
      path: "/drug_labels",
      args: { id: moleculeId },
      params: {
        molecule_id: `eq.${moleculeId}`,
        contraindications: "not.is.null",
        select: "molecule_id,contraindications,label_date",
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getCompetitiveLandscape(
    indication: string,
  ): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "molecules.getCompetitiveLandscape",
      path: "/competitive_scores",
      args: { indication },
      params: {
        therapeutic_areas: `cs.{${indication}}`,
        order: "competitive_score.desc",
        limit: "50",
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getResolutionQueue(
    opts: { limit?: number } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "molecules.getResolutionQueue",
      path: "/resolution_queue",
      args: { limit: opts.limit ?? 100 },
      params: { limit: String(opts.limit ?? 100), order: "queued_at.desc" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }
}
