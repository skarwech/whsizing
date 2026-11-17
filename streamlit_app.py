"""Streamlit Community Cloud entry point: the public demo of whsizing on synthetic data.

Deploy it with "Main file path: streamlit_app.py" (docs/DEPLOY_STREAMLIT.md). The hosted app is
demo-only (`WHSIZING_DEMO_ONLY=1`): no upload, no typed server path, and the data is a fictitious
e-commerce site generated on the first visit, so no client data ever reaches the platform. To run
the full app on your own machine use `just app` (`src/whsizing/app/Home.py`).

The pages are the app's own files (`src/whsizing/app/pages/`), shown through `st.navigation`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("WHSIZING_DEMO_ONLY", "1")
os.environ.setdefault("WHSIZING_RUNS", str(Path(tempfile.gettempdir()) / "whsizing-demo" / "runs"))
os.environ.setdefault("WHSIZING_CATALOG", str(ROOT / "catalog"))
if importlib.util.find_spec("whsizing") is None:  # dependencies installed, the project itself not
    sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

APP = "src/whsizing/app"  # keep in step with whsizing.app.demo_ui.APP (a test checks it)
PAGES = (
    ("Home.py", "Home", "home", "🏭"),
    ("pages/1_Upload.py", "Upload", "upload", "📥"),
    ("pages/2_Data_quality.py", "Data quality", "data-quality", "✅"),
    ("pages/3_Demand_profile.py", "Demand profile", "demand-profile", "📈"),
    ("pages/4_Design_basis.py", "Design basis", "design-basis", "📐"),
    ("pages/5_Scenarios.py", "Scenarios", "scenarios", "🧩"),
    ("pages/6_Results.py", "Results", "results", "📊"),
)

st.navigation(
    [
        st.Page(f"{APP}/{path}", title=title, icon=icon, url_path=url, default=url == "home")
        for path, title, url, icon in PAGES
    ]
).run()
