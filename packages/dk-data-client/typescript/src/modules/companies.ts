/** Company read surface — mirrors the Python companies module. */

import { ModuleBase } from "./_base.js";

export class CompaniesModule extends ModuleBase {
  async resolve(name: string, opts: { hint?: string } = {}): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { name_or_id: name };
    if (opts.hint) body.hint = opts.hint;
    return (await this.call({
      method: "companies.resolve",
      path: "/data-platform/companies/resolve",
      args: { name, hint: opts.hint },
      httpMethod: "POST",
      jsonBody: body,
    })) as Record<string, unknown>;
  }

  async get(companyId: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "companies.get",
      path: "/companies",
      args: { id: companyId },
      params: { company_id: `eq.${companyId}`, limit: "1" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }

  async getPipeline(companyId: string): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "companies.getPipeline",
      path: "/company_pipeline",
      args: { id: companyId },
      params: { company_id: `eq.${companyId}` },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }
}
