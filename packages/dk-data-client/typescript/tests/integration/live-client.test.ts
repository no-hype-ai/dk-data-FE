import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { DkDataClient } from "../../src/client.js";
import { DkDataError } from "../../src/errors.js";

const INTEGRATION_URL = process.env.DK_DATA_INTEGRATION_URL;
const INTEGRATION_KEY = process.env.DK_DATA_INTEGRATION_KEY;

const describeIfStack =
  INTEGRATION_URL && INTEGRATION_KEY ? describe : describe.skip;

describeIfStack("integration: dk-data-client live", () => {
  let client: DkDataClient;

  beforeAll(() => {
    client = new DkDataClient({
      meteringProxyUrl: INTEGRATION_URL ?? "http://localhost:3001",
      apiKey: INTEGRATION_KEY ?? "test",
      fallbackMode: "strict",
      cacheBackend: "none",
      clientName: "integration-test",
    });
    client.setTelemetryEnabled(false);
  });

  afterAll(async () => {
    await client.close();
  });

  it("health returns a payload", async () => {
    const result = await client.health();
    expect(result).toBeDefined();
  });

  it("catalog returns something", async () => {
    const result = await client.catalog();
    expect(result).toBeDefined();
  });

  it("get known molecule CHEMBL25 returns aspirin", async () => {
    const result = (await client.molecules.get("CHEMBL25")) as {
      molecule_id?: string;
      canonical_name?: string;
    };
    expect(result.molecule_id).toBe("CHEMBL25");
    expect(result.canonical_name?.toLowerCase()).toContain("aspirin");
  });

  it("get unknown molecule throws in strict mode", async () => {
    await expect(client.molecules.get("CHEMBL999999")).rejects.toBeInstanceOf(
      DkDataError,
    );
  });

  it("search by name returns a list", async () => {
    const results = await client.molecules.search("aspirin", { limit: 5 });
    expect(Array.isArray(results)).toBe(true);
  });
});
