import importlib
import sys

# At import time, ensure a clean models module is available at the name 'dashboard.models'.
# This avoids runtime issues if dashboard/models.py is temporarily inconsistent in the repo.
try:
    models_fix = importlib.import_module("dashboard.models_fix")
    # make the clean module available under the canonical name
    sys.modules.setdefault("dashboard.models", models_fix)
except Exception:
    # if anything goes wrong, fail silently — code that needs models will raise as normal
    pass

