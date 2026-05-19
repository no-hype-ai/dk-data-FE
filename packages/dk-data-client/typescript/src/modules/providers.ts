/** Healthcare provider read surface. */

import { ModuleBase } from "./_base.js";

export class ProvidersModule extends ModuleBase {
  async resolve(
    npiOrName: string,
    opts: { hint?: string } = {},
  ): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { name_or_id: npiOrName };
    if (opts.hint) body.hint = opts.hint;
    return (await this.call({
      method: "providers.resolve",
      path: "/data-platform/providers/resolve",
      args: { npiOrName, hint: opts.hint },
      httpMethod: "POST",
      jsonBody: body,
    })) as Record<string, unknown>;
  }

  async get(providerId: string): Promise<Record<string, unknown>> {
    const rows = (await this.call({
      method: "providers.get",
      path: "/providers",
      args: { id: providerId },
      params: { provider_id: `eq.${providerId}`, limit: "1" },
    })) as Array<Record<string, unknown>>;
    return Array.isArray(rows) && rows.length > 0 ? rows[0]! : {};
  }
}
