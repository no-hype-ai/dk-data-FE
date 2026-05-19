/** Patents / IP read surface. */

import { ModuleBase } from "./_base.js";

export class PatentsModule extends ModuleBase {
  async search(
    opts: { query?: string; assignee?: string; limit?: number } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const params: Record<string, string> = {
      select:
        "patent_id,title,assignee,filing_date,publication_date,jurisdiction",
      limit: String(opts.limit ?? 25),
      order: "filing_date.desc",
    };
    if (opts.query) params.title = `ilike.*${opts.query}*`;
    if (opts.assignee) params.assignee = `ilike.*${opts.assignee}*`;
    const data = (await this.call({
      method: "patents.search",
      path: "/patents",
      args: {
        query: opts.query,
        assignee: opts.assignee,
        limit: opts.limit ?? 25,
      },
      params,
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getByMolecule(moleculeId: string): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "patents.getByMolecule",
      path: "/patents",
      args: { moleculeId },
      params: {
        molecule_id: `eq.${moleculeId}`,
        order: "filing_date.desc",
        limit: "100",
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }
}
