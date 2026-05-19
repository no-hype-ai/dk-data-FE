/** Publications / literature read surface. */

import { ModuleBase } from "./_base.js";

export class PublicationsModule extends ModuleBase {
  async search(
    query: string,
    opts: { limit?: number; since?: string } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const params: Record<string, string> = {
      select: "publication_id,title,doi,pmid,published_at,journal",
      title: `ilike.*${query}*`,
      order: "published_at.desc",
      limit: String(opts.limit ?? 25),
    };
    if (opts.since) params.published_at = `gte.${opts.since}`;
    const data = (await this.call({
      method: "publications.search",
      path: "/publications",
      args: { query, limit: opts.limit ?? 25, since: opts.since },
      params,
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getByMolecule(moleculeId: string): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "publications.getByMolecule",
      path: "/publications",
      args: { moleculeId },
      params: {
        molecule_id: `eq.${moleculeId}`,
        order: "published_at.desc",
        limit: "100",
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }

  async getPubMed(pmid: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "publications.getPubMed",
      path: "/pubmed_articles",
      args: { pmid },
      params: { pmid: `eq.${pmid}`, limit: "1" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }

  async getOpenAlex(workId: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "publications.getOpenAlex",
      path: "/publications",
      args: { workId },
      params: { openalex_id: `eq.${workId}`, limit: "1" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }
}
