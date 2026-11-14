import { useState } from "react";
import structuredSample from "../../../examples/postal-address/structured.xml?raw";
import hybridSample from "../../../examples/postal-address/hybrid.xml?raw";
import problemsSample from "../../../examples/postal-address/problems.xml?raw";

const SAMPLES = [
  { id: "structured", label: "Fully structured", xml: structuredSample },
  { id: "hybrid", label: "Hybrid", xml: hybridSample },
  { id: "problems", label: "With problems", xml: problemsSample },
];

const FORMAT_LABELS = { structured: "STRUCTURED", hybrid: "HYBRID", unstructured: "UNSTRUCTURED" };

export default function AddressCheckPanel({ api }) {
  const [xml, setXml] = useState("");
  const [enforce, setEnforce] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function reset() {
    setResult(null);
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    reset();
    setLoading(true);
    try {
      const response = await fetch(`${api}/checks/postal-address`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ xml, enforce_unstructured_removal: enforce }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Address check failed.");
      setResult(data);
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const parseFailed = result && result.kind !== "postal_address_check";

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> CBPR+ USAGE RULES</div>
        <h1>Postal address check</h1>
        <p>An XSD accepts addresses that CBPR+ rejects. This check classifies every <code>PstlAdr</code> as structured, hybrid or unstructured and explains what to fix. It needs no schema file and no model.</p>
      </div>
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">MESSAGE INPUT</div><h3>pacs.008 or any message with addresses</h3></div><span className="local-tag"><span className="status-dot green" />DETERMINISTIC</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="address-xml">XML document</label>
            <div className="editor-toolbar-actions">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setXml(sample.xml); reset(); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="address-xml" className="code-editor" value={xml} onChange={(event) => { setXml(event.target.value); reset(); }} placeholder={"Paste synthetic ISO 20022 XML, or load a sample above."} spellCheck="false" required />
          <label className="check-option"><input type="checkbox" checked={enforce} onChange={(event) => { setEnforce(event.target.checked); reset(); }} /> Treat unstructured addresses as errors (simulate the removal deadline)</label>
          <button className="button-primary submit-button" type="submit" disabled={loading || !xml.trim()}>{loading ? "Checking…" : "Check postal addresses"}<span aria-hidden="true">→</span></button>
          <p className="form-footnote">Covers CBPR+ postal address rules only. It does not validate the rest of the message.</p>
        </form>
        <aside className="result-column">
          <div className={`surface-card result-card ${result && !parseFailed ? (result.compliant ? "result-valid" : "result-invalid") : ""}`} aria-live="polite">
            <div className="eyebrow">CHECK RESULT</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">⌂</div><h3>Load a sample to start</h3><p>Try “With problems” to see unstructured addresses, a missing country and a post code inside the town name.</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Check unavailable</h3><p>{error}</p></div>}
            {parseFailed && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>{result.kind === "malformed_xml" ? "Malformed XML" : "Unsupported XML"}</h3>{result.errors.map((item, index) => <div className="diagnostic" key={index}><strong>{item.code}</strong><p>{item.message}</p></div>)}</div>}
            {result && !parseFailed && <AddressReport result={result} />}
          </div>
          <div className="notice-card"><span className="notice-mark">i</span><div><strong>Deadline deferred</strong><p>Swift planned to remove unstructured addresses on 14 November 2026, then deferred it on 27 August 2026; a new date is due by December. <a href={result?.unstructured_removal?.source_url || "https://www.swift.com/insights/news/swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages"} target="_blank" rel="noreferrer">Swift announcement ↗</a></p></div></div>
        </aside>
      </div>
    </section>
  );
}

function AddressReport({ result }) {
  const { summary } = result;
  if (!result.in_scope) {
    return <div className="result-message"><span className="result-symbol">–</span><h3>Out of scope</h3><p><code>{result.message_id}</code> is a reporting or admin message; the CBPR+ address requirement does not apply to it.</p></div>;
  }
  return (
    <div className="result-message">
      <span className="result-symbol">{result.compliant ? "✓" : "!"}</span>
      <h3>{summary.addresses === 0 ? "No postal addresses found" : result.compliant ? "Addresses meet CBPR+ rules" : "Addresses need fixing"}</h3>
      <p>{result.message_id ? <code>{result.message_id}</code> : "Unknown message type"} · {summary.addresses} address{summary.addresses === 1 ? "" : "es"} · {summary.errors} error{summary.errors === 1 ? "" : "s"} · {summary.warnings} warning{summary.warnings === 1 ? "" : "s"}</p>
      {result.addresses.map((address) => (
        <div className="address-block" key={address.xpath}>
          <div className="address-heading"><strong>{address.role_label}</strong><span className={`format-badge format-${address.format}`}>{FORMAT_LABELS[address.format]}</span></div>
          {address.findings.length === 0 && <p className="address-ok">No findings.</p>}
          {address.findings.map((finding, index) => (
            <div className={`diagnostic severity-${finding.severity}`} key={`${finding.rule}-${index}`}>
              <strong>{finding.severity.toUpperCase()} · {finding.rule}</strong>
              <p>{finding.message}</p>
              {finding.suggestion && <p className="finding-fix">Fix: {finding.suggestion}</p>}
              <small>{finding.xpath}</small>
            </div>
          ))}
        </div>
      ))}
      {result.addresses_truncated && <p className="address-ok">Only the first {result.addresses.length} addresses are shown.</p>}
    </div>
  );
}
