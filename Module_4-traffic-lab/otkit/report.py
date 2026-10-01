"""
Self-contained HTML reports (no internet needed, images embedded).
Every otlab analysis command writes one; they double as lab deliverables.
"""
import base64
import datetime as dt
import html
import io

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b2430;--muted:#5b6675;--line:#dde2e8;--accent:#0b5cad;
--crit:#b3261e;--high:#c2410c;--med:#a16207;--low:#2563eb;--ok:#15803d;--code:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1b2129;--ink:#e6e9ee;--muted:#9aa4b2;--line:#2c3440;
--accent:#6cb0ff;--code:#232b35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
header{border-bottom:3px solid var(--accent);margin-bottom:18px;padding-bottom:10px}
h1{margin:0 0 4px;font-size:1.6rem}h2{margin:30px 0 10px;font-size:1.2rem;border-left:4px solid var(--accent);padding-left:10px}
.sub{color:var(--muted);font-size:.92rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card .v{font-size:1.5rem;font-weight:700}.card .l{color:var(--muted);font-size:.85rem}
.card .n{font-size:.8rem;color:var(--muted)}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:.86rem}th,td{padding:6px 9px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{background:var(--code);position:sticky;top:0}
tr.flag td{background:rgba(179,38,30,.09)}
img{max-width:100%;background:#fff;border-radius:8px;border:1px solid var(--line)}
.callout{border-radius:10px;padding:10px 14px;margin:12px 0;border:1px solid var(--line);background:var(--card)}
.callout.tip{border-left:5px solid var(--ok)}.callout.warn{border-left:5px solid var(--high)}
.callout.info{border-left:5px solid var(--accent)}
code,pre{background:var(--code);border-radius:6px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem}
code{padding:1px 5px}pre{padding:10px 12px;overflow-x:auto;white-space:pre-wrap}
.sev{font-weight:700;padding:2px 8px;border-radius:12px;color:#fff;font-size:.78rem}
.CRITICAL{background:var(--crit)}.HIGH{background:var(--high)}.MEDIUM{background:var(--med)}.LOW{background:var(--low)}
.INFO{background:#6b7280}
.finding{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
.finding h3{margin:0 0 6px;font-size:1.05rem}.finding dl{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;margin:6px 0}
.finding dt{color:var(--muted)}.finding dd{margin:0}
footer{margin-top:40px;color:var(--muted);font-size:.8rem}
"""


def esc(x):
    return html.escape(str(x))


def fig_to_data_uri(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def file_to_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


TITLES = {
    "network_reconnaissance": "Network reconnaissance (port scan)",
    "modbus_register_enumeration": "Modbus register enumeration",
    "unauthorised_write": "Unauthorised Modbus write",
    "plc_program_upload": "PLC program upload",
    "arp_spoofing_mitm": "ARP spoofing / man-in-the-middle",
}


class Report:
    def __init__(self, title, subtitle=""):
        self.title = title
        self.parts = [f"<header><h1>{esc(title)}</h1><div class='sub'>{esc(subtitle)}</div></header>"]

    def h2(self, text):
        self.parts.append(f"<h2>{esc(text)}</h2>")

    def p(self, text, raw=False):
        self.parts.append(f"<p>{text if raw else esc(text)}</p>")

    def callout(self, text, kind="info", raw=False):
        self.parts.append(f"<div class='callout {kind}'>{text if raw else esc(text)}</div>")

    def cards(self, items):
        h = "".join(f"<div class='card'><div class='l'>{esc(l)}</div><div class='v'>{esc(v)}</div>"
                    f"<div class='n'>{esc(n)}</div></div>" for l, v, n in items)
        self.parts.append(f"<div class='cards'>{h}</div>")

    def table(self, df, flag_col=None, max_rows=400, index=False):
        if df is None or len(df) == 0:
            self.p("(nothing to show)")
            return
        d = df.reset_index() if index else df
        cols = list(d.columns)
        head = "".join(f"<th>{esc(c)}</th>" for c in cols)
        body = []
        for _, r in d.head(max_rows).iterrows():
            cls = " class='flag'" if flag_col and bool(r.get(flag_col)) else ""
            body.append(f"<tr{cls}>" + "".join(f"<td>{esc(self._fmt(r[c]))}</td>" for c in cols) + "</tr>")
        more = f"<p class='sub'>... {len(d) - max_rows} more rows in the CSV file.</p>" if len(d) > max_rows else ""
        self.parts.append(f"<div class='tbl'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>{more}")

    @staticmethod
    def _fmt(v):
        if isinstance(v, float):
            return f"{v:,.2f}" if abs(v) < 1e6 else f"{v:,.0f}"
        return v

    def image(self, uri, alt=""):
        self.parts.append(f"<p><img src='{uri}' alt='{esc(alt)}'></p>")

    def figure(self, fig, alt=""):
        import matplotlib.pyplot as plt
        self.image(fig_to_data_uri(fig), alt)
        plt.close(fig)

    def code(self, text):
        self.parts.append(f"<pre>{esc(text)}</pre>")

    def raw(self, h):
        self.parts.append(h)

    def finding(self, f, n):
        self.parts.append(
            f"<div class='finding'><h3><span class='sev {f['severity']}'>{f['severity']}</span> "
            f"#{n} {esc(TITLES.get(f['attack_type'], f['attack_type'].replace('_', ' ').capitalize()))} <span class='sub'>(rule {f['rule']})</span></h3>"
            f"<dl><dt>When</dt><dd>{f['time_seconds']:.1f} s into the capture ({esc(f['utc_time'])} UTC), "
            f"first packet No. {f['first_packet']}</dd>"
            f"<dt>Source</dt><dd>{esc(f['src_ip'])}</dd><dt>Target</dt><dd>{esc(f['dst_ip'] or '-')}</dd>"
            f"<dt>Evidence</dt><dd>{esc(f['evidence'])}</dd>"
            f"<dt>See it in Wireshark</dt><dd><code>{esc(f['wireshark_filter'])}</code></dd>"
            f"<dt>What it means</dt><dd>{esc(f['what_it_means'])}</dd>"
            f"<dt>What to do</dt><dd>{esc(f['what_to_do'])}</dd></dl></div>")

    def save(self, path):
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
               f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(self.title)}</title>"
               f"<style>{CSS}</style></head><body><main>{''.join(self.parts)}"
               f"<footer>Generated by otlab (Module 4 OT Traffic Analysis Lab) on {stamp}.</footer></main></body></html>")
        with open(path, "w") as f:
            f.write(doc)
        return path
