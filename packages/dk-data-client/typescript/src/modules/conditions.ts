/** Condition / indication read surface. */

import { ModuleBase } from "./_base.js";

export class ConditionsModule extends ModuleBase {
  async resolve(
    nameOrCode: string,
    opts: { hint?: string } = {},
  ): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { name_or_id: nameOrCode };
    if (opts.hint) body.hint = opts.hint;
    return (await this.call({
      method: "conditions.resolve",
      path: "/data-platform/conditions/resolve",
      args: { nameOrCode, hint: opts.hint },
      httpMethod: "POST",
      jsonBody: body,
    })) as Record<string, unknown>;
  }

  async search(
    query: string,
    opts: { limit?: number } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const data = (await this.call({
      method: "conditions.search",
      path: "/conditions",
      args: { query, limit: opts.limit ?? 25 },
      params: {
        select: "condition_id,canonical_name,icd10,mesh",
        canonical_name: `ilike.*${query}*`,
        limit: String(opts.limit ?? 25),
      },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(data) ? data : [];
  }
}
