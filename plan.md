# dk-data-FE Platform Status — 2026-04-18

## Session delivery (2026-04-15 through 2026-04-18)

**35+ PRs merged** | **139 CronJobs active** | **~19.4M rows** | **12 Grafana dashboards live**

### Horizons shipped
- **H1** (9 PRs): hardened Job manifests, manifest row-count gate, zip extractor fix, 6 alert rules, CNPG runbook, lessons, labels, procurement, dashboards
- **H2** (7 PRs): SeaweedFS client, WAL backpressure, DLQ/quarantine, integrity pipeline, PgBouncer pool split, observability, SQLMesh audits
- **H3** (5 PRs): per-source dispatcher, source descriptors, admission control, node-taint coordination, per-source DopplerSecrets
- **Wave A** (3 PRs): 24 dashboard panels, 15 source stubs + GH issues, D.1↔D.3 integration
- **Wave B** (5 PRs): 15 new sources onboarded (CMS quality, FDA, international, HCP/research, align existing)

### Cluster state
- 3-node k3s: penguin (control), krang (general), scarecrow (bulk)
- Control-plane taint applied, node labels set
- Migrations 229–237 applied
- WAL pressure: real signal (0.39%)
- DLQ + admission control + source registry operational
- Image: `main-937c9f6` (all Wave B code) — tag updated, ArgoCD deploying

### Data loaded

| Table | Rows | Source |
|---|---|---|
| mol_raw.pubchem | ~15,050,000 | PubChem bulk |
| mol_raw.chembl | ~2,878,000 | ChEMBL molecules |
| mol_raw.sider | ~601,000 | SIDER (validated on unsuspend) |
| mol_raw.uniprot | ~574,600 | UniProt |
| mol_raw.pdb | ~251,800 | PDB structures |
| mol_raw.cdc_vaccines | ~141,000 | CDC vaccines |
| mol_raw.fda_ndc | ~131,900 | FDA NDC directory |
| hcp_raw.research_orgs_ror | 125,065 | Research Orgs ROR |
| mol_raw.chembl_activities | ~24,300 | ChEMBL activities |
| hcs_raw.cms_hrrp | 18,330 | CMS HRRP |
| mol_raw.drugbank | 17,430 | DrugBank |
| hcs_raw.cms_hac_reduction | 3,056 | CMS HAC Reduction |
| mol_raw.orange_book | 2,729 | FDA Orange Book |
| hcs_raw.cms_vbp | 2,455 | CMS VBP |
| mol_raw.ema | 1,116 | EMA medicines |

---

## Remaining work

### Immediate — deploy Wave B image + validate

1. **Image `main-937c9f6` deploying** — tag updated in kustomize overlay. ArgoCD will roll pods. Once live, 8 blocked Wave B sources (FDA enforcement/shortages, WHO GHED, World Bank, OECD, PBS Australia, EMA EPAR, Health Canada DPD) should work on next CronJob fire.

2. **Stale silver/gold transforms** — `mol-transform-silver`, `hcs-transform-silver`, `mol-transform-gold` haven't run since Apr 6 (12 days). Need manual trigger to catch up:
   ```
   kubectl -n dk-data-prod create job --from=cronjob/mol-transform-silver manual-mol-silver
   kubectl -n dk-data-prod create job --from=cronjob/hcs-transform-silver manual-hcs-silver
   kubectl -n dk-data-prod create job --from=cronjob/mol-transform-gold manual-mol-gold
   ```

3. **Fix CI build pipeline** (Fix 3) — `.github/workflows/build-deploy.yaml` needs PR-based manifest update instead of direct push. Branch protection blocks the bot.

### Near-term — source tuning

4. **EMA EPAR URL fix** — code committed (`937c9f6`), deploying with new image. If XLSX URL also 404s, will need manual investigation of current EMA endpoint.

5. **Health Canada DPD URL fix** — `https://health-products.canada.ca/api/drug/allfiles` returns 404. Need to find the current endpoint.

6. **Wave B loader validation** — once new image deploys, trigger all 8 pending sources and verify row counts.

### Follow-ups

7. **Grafana dashboards** ✅ — 12 dashboards synced with Admin-scoped SA token
8. **T4 procurement** — 9 licensed sources (#290–#298) awaiting legal
9. **dk-alchemy dependencies** — #647 grafana-operator (deferred), #649 postgres isolation (Phase 8)
10. **dk-cli** — fully shipped (PRs #4/#5/#6)

---

## Verification checklist

- [x] Migrations 229–237 applied
- [x] WAL pressure returns real signal
- [x] DLQ + admission control operational
- [x] Source registry seeded (5 rows)
- [x] Resource budget seeded (4 keys)
- [x] PgBouncer pool split deployed
- [x] 6 PrometheusRules evaluating
- [x] 12 Grafana dashboards synced
- [x] 139 CronJobs unsuspended
- [x] CMS quality trio loaded (23,841 rows)
- [x] ROR loaded (125,065 rows)
- [x] Sider validated (601K records)
- [x] 7 existing sources validated live
- [ ] Silver/gold transforms caught up (stale 12d)
- [ ] 8 Wave B sources activated (pending image deploy)
- [ ] CI build pipeline fixed (PR-based manifest update)
