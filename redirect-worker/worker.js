// Exit Radar — redirect worker for radar.omdanny.site.
//
// Streamlit Cloud does not support custom domains, so the subdomain
// cannot serve the dashboard directly. This worker redirects every
// path to the Streamlit dashboard home (302). Alert links of the form
// radar.omdanny.site/<ticker> therefore resolve instead of dying;
// per-ticker deep links arrive later, when the app reads a query
// parameter (e.g. ?ticker=TSLAx) — until then the ticker path is
// intentionally dropped, not faked.
const TARGET = "https://radar-tokenized-stocks.streamlit.app/";

export default {
  async fetch() {
    return Response.redirect(TARGET, 302);
  },
};
