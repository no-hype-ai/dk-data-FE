"""MCP adapter registry."""

from .fda_drugs import FdaDrugsTool
from .pdb_structures import PdbStructuresTool
from .orcid import OrcidTool
from .cms_part_d_spending import CmsPartDSpendingTool
from .hta_decisions import HtaDecisionsTool
from .ema import EmaTool
from .cochrane import CochraneTool
from .ttd import TtdTool
from .openfda_labels import OpenFDALabelsTool

__all__ = [
    "FdaDrugsTool",
    "PdbStructuresTool",
    "OrcidTool",
    "CmsPartDSpendingTool",
    "HtaDecisionsTool",
    "EmaTool",
    "CochraneTool",
    "TtdTool",
    "OpenFDALabelsTool",
]
