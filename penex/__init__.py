"""PenaltyExposure Modeler - statutory privacy-penalty exposure bands.

    from penex import Registry, Precedents, model_case
    reg, pr = Registry(), Precedents()
    result = model_case(case_dict, reg, pr)

See README.md for the method and its limitations.  Prototype output is triage
material, not legal advice.
"""
from .model import FACTOR_WEIGHTS, factor_multiplier, model_case
from .parser import draft_case_spec, parse_text
from .precedents import Precedents
from .report import render_markdown
from .statutes import Cap, Registry

__version__ = "0.1.0"

__all__ = [
    "Registry", "Precedents", "Cap", "model_case", "factor_multiplier",
    "FACTOR_WEIGHTS", "parse_text", "draft_case_spec", "render_markdown",
    "__version__",
]
