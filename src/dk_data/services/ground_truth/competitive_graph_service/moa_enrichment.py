"""MOA enrichment table.

Maps caller-friendly MOA text (e.g. "TNF-alpha inhibitor") to the strict
OpenFDA pharm_class string, ChEMBL-style protein targets, and ATC-class
prefix. The graph service uses this to fill in fields the caller didn't
provide so the MOA / TARGET / CLASS fan-out branches actually run.

Notes:
- ATC prefixes are 4-5 char (drug class). Used for OpenFDA pharm_class_epc
  fallback when the EPC string fails to match.
- Targets are HGNC gene symbols (or viral protein names for antivirals).
- `fda_pharm_class_epc` strings are the canonical "[EPC]" labels OpenFDA
  publishes; we omit the trailing " [EPC]" since the client appends it.
- Aliases that the loose-match suffix-stripping in `lookup_moa()` already
  resolves (e.g. "tnf inhibitor" → "tnf-alpha inhibitor") are omitted to
  keep the table compact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MoaEnrichment:
    fda_pharm_class_moa: str | None = None
    fda_pharm_class_epc: str | None = None
    targets: tuple = ()
    atc_prefix: str | None = None


MOA_ENRICHMENT: dict[str, MoaEnrichment] = {
    # ─────────────────────────── Oncology — targeted therapy ───────────────
    "egfr inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Epidermal Growth Factor Receptor Inhibitor",
        targets=("EGFR",),
        atc_prefix="L01EB",
    ),
    "her2 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="HER2/Neu Receptor Antagonist",
        targets=("ERBB2",),
        atc_prefix="L01FD",
    ),
    "alk inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Anaplastic Lymphoma Kinase Inhibitor",
        targets=("ALK",),
        atc_prefix="L01ED",
    ),
    "braf inhibitor": MoaEnrichment(
        fda_pharm_class_epc="B-raf Kinase Inhibitor",
        targets=("BRAF",),
        atc_prefix="L01EC",
    ),
    "mek inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Mitogen-activated Extracellular Signal Regulated Kinase Inhibitor",
        targets=("MAP2K1", "MAP2K2"),
        atc_prefix="L01EE",
    ),
    "kras inhibitor": MoaEnrichment(
        fda_pharm_class_epc="KRAS G12C Inhibitor",
        targets=("KRAS",),
        atc_prefix="L01XX",
    ),
    "bcr-abl inhibitor": MoaEnrichment(
        fda_pharm_class_epc="BCR-ABL Tyrosine Kinase Inhibitor",
        targets=("ABL1",),
        atc_prefix="L01EA",
    ),
    "cdk4/6 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Cyclin-Dependent Kinase 4 and 6 Inhibitor",
        targets=("CDK4", "CDK6"),
        atc_prefix="L01EF",
    ),
    "parp inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Poly(ADP-Ribose) Polymerase Inhibitor",
        targets=("PARP1", "PARP2"),
        atc_prefix="L01XK",
    ),
    "mtor inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Mammalian Target of Rapamycin Kinase Inhibitor",
        targets=("MTOR",),
        atc_prefix="L01EG",
    ),
    "vegfr inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Vascular Endothelial Growth Factor Receptor Inhibitor",
        targets=("KDR", "FLT1", "FLT4"),
        atc_prefix="L01EK",
    ),
    "vegf inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Vascular Endothelial Growth Factor-directed Antibody",
        targets=("VEGFA",),
        atc_prefix="L01FG",
    ),
    "btk inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Bruton's Tyrosine Kinase Inhibitor",
        targets=("BTK",),
        atc_prefix="L01EL",
    ),
    "bcl-2 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="B-Cell Lymphoma-2 (BCL-2) Inhibitor",
        targets=("BCL2",),
        atc_prefix="L01XX",
    ),
    "pi3k inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Phosphatidylinositol 3-Kinase Inhibitor",
        targets=("PIK3CA", "PIK3CD"),
        atc_prefix="L01EM",
    ),
    "fgfr inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Fibroblast Growth Factor Receptor Inhibitor",
        targets=("FGFR1", "FGFR2", "FGFR3"),
        atc_prefix="L01EN",
    ),
    "ret inhibitor": MoaEnrichment(
        fda_pharm_class_epc="RET Tyrosine Kinase Inhibitor",
        targets=("RET",),
        atc_prefix="L01EX",
    ),
    "met inhibitor": MoaEnrichment(
        fda_pharm_class_epc="MET Tyrosine Kinase Inhibitor",
        targets=("MET",),
        atc_prefix="L01EX",
    ),
    "trk inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Tropomyosin Receptor Kinase Inhibitor",
        targets=("NTRK1", "NTRK2", "NTRK3"),
        atc_prefix="L01EX",
    ),
    "hdac inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Histone Deacetylase Inhibitor",
        targets=("HDAC1", "HDAC2", "HDAC3"),
        atc_prefix="L01XH",
    ),
    "idh1 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Isocitrate Dehydrogenase-1 Inhibitor",
        targets=("IDH1",),
        atc_prefix="L01XX",
    ),
    "idh2 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Isocitrate Dehydrogenase-2 Inhibitor",
        targets=("IDH2",),
        atc_prefix="L01XX",
    ),
    "ezh2 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="EZH2 Inhibitor",
        targets=("EZH2",),
        atc_prefix="L01XX",
    ),
    # ─────────────────────────── Oncology — immunotherapy ──────────────────
    "pd-1 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Programmed Death Receptor-1 Blocking Antibody",
        targets=("PDCD1",),
        atc_prefix="L01FF",
    ),
    "pd-l1 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Programmed Death Ligand 1 Blocking Antibody",
        targets=("CD274",),
        atc_prefix="L01FF",
    ),
    "ctla-4 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Cytotoxic T-Lymphocyte Antigen 4-blocking Antibody",
        targets=("CTLA4",),
        atc_prefix="L01FX",
    ),
    "lag-3 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Lymphocyte Activation Gene-3 Blocking Antibody",
        targets=("LAG3",),
        atc_prefix="L01FX",
    ),
    "cd19 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="CD19-directed Antibody",
        targets=("CD19",),
        atc_prefix="L01FX",
    ),
    "cd20 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="CD20-directed Cytolytic Antibody",
        targets=("MS4A1",),
        atc_prefix="L01FA",
    ),
    "cd22 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="CD22-directed Antibody-Drug Conjugate",
        targets=("CD22",),
        atc_prefix="L01XC",
    ),
    "cd30 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="CD30-directed Antibody-Drug Conjugate",
        targets=("TNFRSF8",),
        atc_prefix="L01XC",
    ),
    "cd38 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="CD38-directed Cytolytic Antibody",
        targets=("CD38",),
        atc_prefix="L01FC",
    ),
    "bcma inhibitor": MoaEnrichment(
        fda_pharm_class_epc="B-Cell Maturation Antigen-directed Antibody-Drug Conjugate",
        targets=("TNFRSF17",),
        atc_prefix="L01FX",
    ),
    # ─────────────────────────── Immunology / Rheumatology ─────────────────
    "tnf-alpha inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Tumor Necrosis Factor Blocker",
        targets=("TNF",),
        atc_prefix="L04AB",
    ),
    "il-1 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-1 Blocker",
        targets=("IL1A", "IL1B"),
        atc_prefix="L04AC",
    ),
    "il-6 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-6 Receptor Antagonist",
        targets=("IL6R",),
        atc_prefix="L04AC",
    ),
    "il-17 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-17A Antagonist",
        targets=("IL17A",),
        atc_prefix="L04AC",
    ),
    "il-23 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-23 Antagonist",
        targets=("IL23A",),
        atc_prefix="L04AC",
    ),
    "il-12/23 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-12 and Interleukin-23 Antagonist",
        targets=("IL12B",),
        atc_prefix="L04AC",
    ),
    "il-4 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-4 Receptor Alpha Antagonist",
        targets=("IL4R",),
        atc_prefix="D11AH",
    ),
    "il-5 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-5 Antagonist",
        targets=("IL5",),
        atc_prefix="R03DX",
    ),
    "il-13 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Interleukin-13 Antagonist",
        targets=("IL13",),
        atc_prefix="D11AH",
    ),
    "ige inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Immunoglobulin E-directed Antibody",
        targets=("IGHE",),
        atc_prefix="R03DX",
    ),
    "jak inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Janus Kinase Inhibitor",
        targets=("JAK1", "JAK2", "JAK3"),
        atc_prefix="L04AF",
    ),
    "s1p modulator": MoaEnrichment(
        fda_pharm_class_epc="Sphingosine 1-Phosphate Receptor Modulator",
        targets=("S1PR1",),
        atc_prefix="L04AE",
    ),
    "blys inhibitor": MoaEnrichment(
        fda_pharm_class_epc="B Lymphocyte Stimulator-specific Inhibitor",
        targets=("TNFSF13B",),
        atc_prefix="L04AG",
    ),
    "c5 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Complement Inhibitor",
        targets=("C5",),
        atc_prefix="L04AJ",
    ),
    "alpha-4 integrin inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Integrin Receptor Antagonist",
        targets=("ITGA4",),
        atc_prefix="L04AG",
    ),
    # ─────────────────────────── Metabolic / Endocrine ─────────────────────
    "dpp-4 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Dipeptidyl Peptidase 4 Inhibitor",
        targets=("DPP4",),
        atc_prefix="A10BH",
    ),
    "glp-1 agonist": MoaEnrichment(
        fda_pharm_class_epc="Glucagon-Like Peptide-1 (GLP-1) Receptor Agonist",
        targets=("GLP1R",),
        atc_prefix="A10BJ",
    ),
    "sglt2 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Sodium-Glucose Cotransporter 2 Inhibitor",
        targets=("SLC5A2",),
        atc_prefix="A10BK",
    ),
    "biguanide": MoaEnrichment(
        fda_pharm_class_epc="Biguanide",
        targets=(),
        atc_prefix="A10BA",
    ),
    "sulfonylurea": MoaEnrichment(
        fda_pharm_class_epc="Sulfonylurea",
        targets=("ABCC8",),
        atc_prefix="A10BB",
    ),
    "thiazolidinedione": MoaEnrichment(
        fda_pharm_class_epc="Peroxisome Proliferator Activated Receptor Gamma Agonist",
        targets=("PPARG",),
        atc_prefix="A10BG",
    ),
    # ─────────────────────────── Cardiovascular ────────────────────────────
    "ace inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Angiotensin Converting Enzyme Inhibitor",
        targets=("ACE",),
        atc_prefix="C09AA",
    ),
    "arb": MoaEnrichment(
        fda_pharm_class_epc="Angiotensin 2 Receptor Blocker",
        targets=("AGTR1",),
        atc_prefix="C09CA",
    ),
    "beta blocker": MoaEnrichment(
        fda_pharm_class_epc="beta-Adrenergic Blocker",
        targets=("ADRB1", "ADRB2"),
        atc_prefix="C07AA",
    ),
    "calcium channel blocker": MoaEnrichment(
        fda_pharm_class_epc="Calcium Channel Blocker",
        targets=("CACNA1C",),
        atc_prefix="C08CA",
    ),
    "statin": MoaEnrichment(
        fda_pharm_class_epc="HMG-CoA Reductase Inhibitor",
        targets=("HMGCR",),
        atc_prefix="C10AA",
    ),
    "pcsk9 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="PCSK9 Inhibitor",
        targets=("PCSK9",),
        atc_prefix="C10AX",
    ),
    "p2y12 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="P2Y12 Platelet Inhibitor",
        targets=("P2RY12",),
        atc_prefix="B01AC",
    ),
    "factor xa inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Factor Xa Inhibitor",
        targets=("F10",),
        atc_prefix="B01AF",
    ),
    "direct thrombin inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Direct Thrombin Inhibitor",
        targets=("F2",),
        atc_prefix="B01AE",
    ),
    "vitamin k antagonist": MoaEnrichment(
        fda_pharm_class_epc="Vitamin K Inhibitor",
        targets=("VKORC1",),
        atc_prefix="B01AA",
    ),
    "mineralocorticoid receptor antagonist": MoaEnrichment(
        fda_pharm_class_epc="Mineralocorticoid Receptor Antagonist",
        targets=("NR3C2",),
        atc_prefix="C03DA",
    ),
    # ─────────────────────────── CNS / Psychiatry / Neuro ──────────────────
    "ssri": MoaEnrichment(
        fda_pharm_class_epc="Selective Serotonin Reuptake Inhibitor",
        targets=("SLC6A4",),
        atc_prefix="N06AB",
    ),
    "snri": MoaEnrichment(
        fda_pharm_class_epc="Serotonin and Norepinephrine Reuptake Inhibitor",
        targets=("SLC6A4", "SLC6A2"),
        atc_prefix="N06AX",
    ),
    "tca": MoaEnrichment(
        fda_pharm_class_epc="Tricyclic Antidepressant",
        targets=("SLC6A2", "SLC6A4"),
        atc_prefix="N06AA",
    ),
    "atypical antipsychotic": MoaEnrichment(
        fda_pharm_class_epc="Atypical Antipsychotic",
        targets=("DRD2", "HTR2A"),
        atc_prefix="N05AH",
    ),
    "ache inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Acetylcholinesterase Inhibitor",
        targets=("ACHE",),
        atc_prefix="N06DA",
    ),
    "nmda antagonist": MoaEnrichment(
        fda_pharm_class_epc="N-methyl-D-aspartate Receptor Antagonist",
        targets=("GRIN1", "GRIN2A", "GRIN2B"),
        atc_prefix="N06DX",
    ),
    "dopamine agonist": MoaEnrichment(
        fda_pharm_class_epc="Dopamine Agonist",
        targets=("DRD2", "DRD3"),
        atc_prefix="N04BC",
    ),
    "mao-b inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Monoamine Oxidase Type B Inhibitor",
        targets=("MAOB",),
        atc_prefix="N04BD",
    ),
    "benzodiazepine": MoaEnrichment(
        fda_pharm_class_epc="Benzodiazepine",
        targets=("GABRA1",),
        atc_prefix="N05BA",
    ),
    # ─────────────────────────── Migraine ──────────────────────────────────
    "cgrp inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Calcitonin Gene-Related Peptide Receptor Antagonist",
        targets=("CALCRL", "CALCA"),
        atc_prefix="N02CD",
    ),
    "triptan": MoaEnrichment(
        fda_pharm_class_epc="Serotonin-1B and Serotonin-1D Receptor Agonist",
        targets=("HTR1B", "HTR1D"),
        atc_prefix="N02CC",
    ),
    # ─────────────────────────── Anti-infectives ───────────────────────────
    "hiv nrti": MoaEnrichment(
        fda_pharm_class_epc="HIV Nucleoside Analog Reverse Transcriptase Inhibitor",
        targets=("HIV-RT",),
        atc_prefix="J05AF",
    ),
    "hiv nnrti": MoaEnrichment(
        fda_pharm_class_epc="HIV Non-Nucleoside Analog Reverse Transcriptase Inhibitor",
        targets=("HIV-RT",),
        atc_prefix="J05AG",
    ),
    "hiv protease inhibitor": MoaEnrichment(
        fda_pharm_class_epc="HIV Protease Inhibitor",
        targets=("HIV-PR",),
        atc_prefix="J05AE",
    ),
    "hiv integrase inhibitor": MoaEnrichment(
        fda_pharm_class_epc="HIV Integrase Strand Transfer Inhibitor",
        targets=("HIV-IN",),
        atc_prefix="J05AJ",
    ),
    "hcv ns5a inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Hepatitis C Virus NS5A Inhibitor",
        targets=("HCV-NS5A",),
        atc_prefix="J05AP",
    ),
    "hcv ns5b inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Hepatitis C Virus NS5B Polymerase Inhibitor",
        targets=("HCV-NS5B",),
        atc_prefix="J05AP",
    ),
    "hcv protease inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Hepatitis C Virus NS3/4A Protease Inhibitor",
        targets=("HCV-NS3",),
        atc_prefix="J05AP",
    ),
    "neuraminidase inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Influenza Virus Neuraminidase Inhibitor",
        targets=("INF-NA",),
        atc_prefix="J05AH",
    ),
    # ─────────────────────────── Respiratory ───────────────────────────────
    "inhaled corticosteroid": MoaEnrichment(
        fda_pharm_class_epc="Corticosteroid",
        targets=("NR3C1",),
        atc_prefix="R03BA",
    ),
    "laba": MoaEnrichment(
        fda_pharm_class_epc="Long-acting beta2-Adrenergic Agonist",
        targets=("ADRB2",),
        atc_prefix="R03AC",
    ),
    "lama": MoaEnrichment(
        fda_pharm_class_epc="Long-acting Muscarinic Antagonist",
        targets=("CHRM3",),
        atc_prefix="R03BB",
    ),
    "ltra": MoaEnrichment(
        fda_pharm_class_epc="Leukotriene Receptor Antagonist",
        targets=("CYSLTR1",),
        atc_prefix="R03DC",
    ),
    "pde4 inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Phosphodiesterase 4 Inhibitor",
        targets=("PDE4A", "PDE4B"),
        atc_prefix="R03DX",
    ),
    # ─────────────────────────── GI ────────────────────────────────────────
    "proton pump inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Proton Pump Inhibitor",
        targets=("ATP4A",),
        atc_prefix="A02BC",
    ),
    "h2 blocker": MoaEnrichment(
        fda_pharm_class_epc="Histamine-2 Receptor Antagonist",
        targets=("HRH2",),
        atc_prefix="A02BA",
    ),
    "5-ht3 antagonist": MoaEnrichment(
        fda_pharm_class_epc="Serotonin-3 Receptor Antagonist",
        targets=("HTR3A",),
        atc_prefix="A04AA",
    ),
    # ─────────────────────────── Bone / Hormone ────────────────────────────
    "bisphosphonate": MoaEnrichment(
        fda_pharm_class_epc="Bisphosphonate",
        targets=("FDPS",),
        atc_prefix="M05BA",
    ),
    "rankl inhibitor": MoaEnrichment(
        fda_pharm_class_epc="RANK Ligand Inhibitor",
        targets=("TNFSF11",),
        atc_prefix="M05BX",
    ),
    "serm": MoaEnrichment(
        fda_pharm_class_epc="Selective Estrogen Receptor Modulator",
        targets=("ESR1",),
        atc_prefix="G03XC",
    ),
    "aromatase inhibitor": MoaEnrichment(
        fda_pharm_class_epc="Aromatase Inhibitor",
        targets=("CYP19A1",),
        atc_prefix="L02BG",
    ),
    "gnrh agonist": MoaEnrichment(
        fda_pharm_class_epc="Gonadotropin Releasing Hormone Receptor Agonist",
        targets=("GNRHR",),
        atc_prefix="L02AE",
    ),
}


def _normalize_key(moa: str | None) -> str | None:
    if not moa:
        return None
    return moa.strip().lower() or None


def static_lookup(moa: str | None) -> MoaEnrichment | None:
    """Look up MOA in the in-memory static dict only.

    Exact match first; falls back to a loose suffix-stripped match
    (e.g. "TNF antagonist" → "tnf-alpha inhibitor" via prefix match).
    No DB, no external API. Sync, side-effect-free.
    """
    key = _normalize_key(moa)
    if key is None:
        return None
    if key in MOA_ENRICHMENT:
        return MOA_ENRICHMENT[key]
    for suffix in (" inhibitor", " antagonist", " blocker", " agonist"):
        if key.endswith(suffix):
            base = key[: -len(suffix)].strip()
            for k in MOA_ENRICHMENT:
                if k.startswith(base):
                    return MOA_ENRICHMENT[k]
    return None


async def lookup_moa(
    moa: str | None,
    db_pool: Any = None,
    openfda_client: Any = None,
) -> MoaEnrichment | None:
    """Look up MOA across all tiers: static dict → DB cache → external API.

    Tiers:
        1. ``static_lookup``       — fast path, in-memory dict
        2. DB cache                — ``mol_silver.moa_enrichment_cache``
        3. OpenFDA resolver        — persists result (positive OR negative)

    Args:
        moa: free-text MOA, e.g. "TNF-alpha inhibitor", "PD-1 blocker"
        db_pool: asyncpg pool. If None, skip tiers 2 + 3.
        openfda_client: OpenFDAClient. If None, skip tier 3.

    Returns:
        MoaEnrichment on hit; None if all tiers miss.
    """
    # Tier 1: static dict
    hit = static_lookup(moa)
    if hit is not None:
        return hit

    key = _normalize_key(moa)
    if key is None or db_pool is None:
        return None

    # Tier 2: DB cache
    from .moa_enrichment_repo import NEGATIVE_HIT, bump_hit_count, fetch_cached, persist

    cached = await fetch_cached(db_pool, key)
    if cached is NEGATIVE_HIT:
        return None
    if isinstance(cached, MoaEnrichment):
        await bump_hit_count(db_pool, key)
        return cached

    # Tier 3: external resolver (only if client provided)
    if openfda_client is None:
        return None

    from .moa_enrichment_resolver import resolve_from_openfda

    resolved = await resolve_from_openfda(openfda_client, key)
    await persist(db_pool, key, resolved, source="openfda")
    return resolved
