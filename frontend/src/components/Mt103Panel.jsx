import { useState } from "react";
import structuredParties from "../../../examples/mt103/structured-parties.txt?raw";
import legacyFreeText from "../../../examples/mt103/legacy-free-text.txt?raw";

const SAMPLES = [
  { id: "structured", label: "MT103 with 50F/59F", text: structuredParties },
  { id: "legacy", label: "Legacy MT103 (50K/59)", text: legacyFreeText },
];

const STATUS_LABELS = {
  mapped: "MAPPED",
  defaulted: "DEFAULTED",
  unstructured: "UNSTRUCTURED",
  truncated: "TRUNCATED",
  missing: "MISSING",
  unmapped: "NOT CARRIED",
  warning: "CHECK",
};

export default function Mt103Panel({ api }) {
  const [mt, setMt] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setResult(null);
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${api}/convert/mt103`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mt }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Conversion failed.");
      setResult(data);
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const check = result?.cbpr_check;
  const attention = result ? result.report.filter((item) => item.status !== "mapped") : [];

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> MT → MX MIGRATION AID</div>
        <h1>MT103 → pacs.008</h1>
        <p>Paste an MT103 to draft the equivalent CBPR+ pacs.008 and see, field by field, what carries over, what gets a default, what stays unstructured and what is lost. The draft is then checked against CBPR+ rules.</p>
      </div>
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">MT INPUT</div><h3>MT103 text</h3></div><span className="local-tag"><span className="status-dot green" />DETERMINISTIC</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="mt-input">MT103 message</label>
            <div className="editor-toolbar-actions">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setMt(sample.text); setResult(null); setError(""); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="mt-input" className="code-editor" value={mt} onChange={(event) => { setMt(event.target.value); setResult(null); setError(""); }} placeholder={":20:REFERENCE\n:23B:CRED\n:32A:261116EUR1000,\n…"} spellCheck="false" maxLength={20000} required />
          <button className="button-primary submit-button" type="submit" disabled={loading || !mt.trim()}>{loading ? "Converting…" : "Draft pacs.008"}<span aria-hidden="true">→</span></button>
          <p className="form-footnote">A migration aid based on public bank mapping guides, not a certified Swift translation. Use synthetic data only.</p>
        </form>
        <aside className="result-column">
          <div className={`surface-card result-card ${check ? (check.compliant ? "result-valid" : "result-invalid") : ""}`} aria-live="polite">
            <div className="eyebrow">CONVERSION REPORT</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">⇢</div><h3>Load a sample to start</h3><p>The legacy sample shows what an old-style MT103 lacks for CBPR+: no UETR, free-text addresses and a field with no equivalent.</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Cannot read this MT103</h3><p>{error}</p></div>}
            {result && (
              <div className="result-message">
                <span className="result-symbol">{check.compliant ? "✓" : "!"}</span>
                <h3>{check.compliant ? "Draft meets CBPR+ rules" : "Draft needs more data for CBPR+"}</h3>
                <p>{result.report.length} report lines · {attention.length} need attention · CBPR+ {check.summary.errors} error{check.summary.errors === 1 ? "" : "s"}, {check.summary.warnings} warning{check.summary.warnings === 1 ? "" : "s"}</p>
                <div className="address-block">
                  <div className="address-heading"><strong>Field mapping</strong></div>
                  {result.report.map((item, index) => (
                    <div className={`diagnostic mapping-${item.status}`} key={index}>
                      <strong>{item.field} · {STATUS_LABELS[item.status] || item.status.toUpperCase()}</strong>
                      <p>{item.detail}</p>
                      {item.target && <small>→ {item.target}</small>}
                    </div>
                  ))}
                </div>
                {[...check.transactions.flatMap((transaction) => transaction.findings), ...(check.postal_addresses?.addresses || []).flatMap((address) => address.findings)].length > 0 && (
                  <div className="address-block">
                    <div className="address-heading"><strong>CBPR+ check of the draft</strong></div>
                    {[...check.message_findings, ...check.transactions.flatMap((transaction) => transaction.findings), ...(check.postal_addresses?.addresses || []).flatMap((address) => address.findings)].map((finding, index) => (
                      <div className={`diagnostic severity-${finding.severity}`} key={index}><strong>{finding.severity.toUpperCase()} · {finding.rule}</strong><p>{finding.message}</p></div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          {result && <div className="surface-card xml-card"><div className="eyebrow">DRAFT pacs.008.001.08</div><pre className="xml-output">{result.xml}</pre></div>}
        </aside>
      </div>
    </section>
  );
}
