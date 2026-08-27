"""
Streamlit Login Gate -> Embeds the full HTML dashboard

Architecture:
  1. Login screen (username + password from st.secrets)
  2. After login, the sanitised `data/dashboard.html` is rendered
     inline. That HTML is the same polished Leaflet + Chart.js
     dashboard that ships in the full project bundle; the only
     difference is that every embedded `"desc"` JSON field has been
     replaced with a placeholder before being committed to this
     deploy folder.

Why embed the HTML rather than rebuild the dashboard in Python?
  - The HTML dashboard is the visual artefact stakeholders signed off on.
  - Leaflet + Chart.js give a richer experience than pydeck/plotly here.
  - One source of truth: the same HTML file is used for the offline
    dashboard and the gated public deployment.

To re-sanitise after a fresh export from the full project:
    python3 scripts/sanitize.py
"""
import hmac
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


HERE           = Path(__file__).resolve().parent
DASHBOARD_HTML = HERE / "dashboard.html"


# ----------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Minorities Early-Warning — Lahore",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ----------------------------------------------------------------------
# Login gate (username + password via st.secrets)
# ----------------------------------------------------------------------
def _check_login() -> bool:
    def _on_submit() -> None:
        u_in = st.session_state.get("username_input", "")
        p_in = st.session_state.get("password_input", "")
        u_ok = st.secrets.get("username", "")
        p_ok = st.secrets.get("password", "")
        if (u_ok and p_ok
                and hmac.compare_digest(u_in, u_ok)
                and hmac.compare_digest(p_in, p_ok)):
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <style>
          [data-testid="stSidebar"] { display: none !important; }
          [data-testid="stHeader"]  { background: transparent; }
          .main .block-container { padding-top: 3rem; max-width: none; }
          .login-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 16px;
            padding: 2.4rem 2.4rem 2rem 2.4rem;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
          }
          .login-emoji { font-size: 3.4rem; line-height: 1; }
          .login-title {
            margin: 0.4rem 0 0.1rem 0;
            font-size: 1.7rem;
            font-weight: 700;
            color: #0f172a;
          }
          .login-sub {
            color: #64748b;
            margin: 0 0 1.6rem 0;
            font-size: 0.95rem;
          }
          .login-divider {
            border-top: 1px solid #e2e8f0;
            margin: 1.5rem 0 1rem 0;
          }
          .login-footer {
            text-align: center;
            color: #94a3b8;
            font-size: 0.82rem;
            line-height: 1.55;
          }
          .stForm { border: none !important; padding: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 2, 1])
    with center:
        st.markdown(
            """
            <div class="login-card">
              <div style="text-align:center; margin-bottom: 1.4rem;">
                <div class="login-emoji">⚡</div>
                <h1 class="login-title">Minorities Early-Warning</h1>
              </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False, border=False):
            st.text_input(
                "Username",
                key="username_input",
                placeholder="e.g. admin",
                autocomplete="username",
            )
            st.text_input(
                "Password",
                type="password",
                key="password_input",
                placeholder="Enter your password",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "Log in",
                use_container_width=True,
                type="primary",
            )
            if submitted:
                _on_submit()

        if st.session_state.get("authenticated") is False:
            st.error("Incorrect username or password.", icon="🚫")

        if "password" not in st.secrets or "username" not in st.secrets:
            st.warning(
                "Credentials are not configured. Set `username` and "
                "`password` in Streamlit Cloud's Secrets pane (or in a "
                "local `.streamlit/secrets.toml`).",
                icon="⚠️",
            )

        st.markdown("</div>", unsafe_allow_html=True)

    return False


if not _check_login():
    st.stop()


# ----------------------------------------------------------------------
# Logged in — render the embedded dashboard full-bleed
# ----------------------------------------------------------------------
st.markdown(
    """
    <style>
      /* Aggressively kill all Streamlit chrome so the dashboard goes edge-to-edge.
         Selectors cover both the legacy classes and the current
         data-testid hooks (Streamlit >= 1.5x renamed several of these). */
      [data-testid="stAppViewContainer"]   { padding: 0 !important; }
      [data-testid="stHeader"], header[data-testid="stHeader"] {
        display: none !important; height: 0 !important;
      }
      [data-testid="stToolbar"]            { display: none !important; }
      [data-testid="stDecoration"]         { display: none !important; }
      [data-testid="stStatusWidget"]       { display: none !important; }
      [data-testid="stMain"]               { padding: 0 !important; }
      [data-testid="stMainBlockContainer"],
      .stMainBlockContainer,
      .main .block-container,
      .block-container {
        padding: 0 !important; margin: 0 !important; max-width: 100% !important;
      }
      [data-testid="stVerticalBlock"]      { gap: 0 !important; }
      [data-testid="stElementContainer"]   { margin: 0 !important; }
      [data-testid="stSidebar"]            { display: none !important; }
      .stApp > header                      { display: none !important; }
      footer                               { display: none !important; }
      .stApp { background: #f8fafc; }

      /* Floating logout button — compact translucent pill that sits over the
         dark header's top-right corner (header has matching right-padding so
         it never covers the "Top: …" badge). */
      [data-testid="stButton"], .stButton {
        position: fixed !important;
        top: 11px !important;
        right: 16px !important;
        width: auto !important;
        z-index: 100000 !important;
        margin: 0 !important;
      }
      [data-testid="stButton"] button, .stButton button {
        padding: 5px 14px !important;
        min-height: 0 !important;
        font-size: 12px !important;
        line-height: 1.3 !important;
        border-radius: 8px !important;
        background: rgba(255,255,255,0.10) !important;
        backdrop-filter: blur(6px) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255,255,255,0.28) !important;
        box-shadow: 0 2px 8px rgba(15,23,42,0.20) !important;
        font-weight: 500 !important;
      }
      [data-testid="stButton"] button:hover, .stButton button:hover {
        background: rgba(255,255,255,0.20) !important;
        border-color: rgba(255,255,255,0.50) !important;
        color: #ffffff !important;
      }

      /* Make the embedded iframe fill the viewport */
      iframe { width: 100% !important; height: 100vh !important; border: 0 !important; display: block !important; }
      [data-testid="stIFrameResizerAnchor"] { display: none !important; }
      [data-testid="stCustomComponentV1"] { width: 100% !important; height: 100vh !important; }
      .element-container:has(iframe) { padding: 0 !important; margin: 0 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Floating logout button (CSS above positions it absolutely)
if st.button("Log out", key="logout_btn"):
    st.session_state["authenticated"] = False
    st.rerun()

if not DASHBOARD_HTML.exists():
    st.error(
        f"Dashboard file not found at `{DASHBOARD_HTML}`. "
        "Run `python3 scripts/sanitize.py` from the project root to "
        "produce a sanitised copy from the full project bundle."
    )
    st.stop()

html = DASHBOARD_HTML.read_text(encoding="utf-8")
# Use a tall fixed height so the iframe fills the viewport;
# the CSS above stretches the iframe to 100vh.
components.html(html, height=1080, scrolling=True)
