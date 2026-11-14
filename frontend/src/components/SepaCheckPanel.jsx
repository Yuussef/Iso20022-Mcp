import { useState } from "react";
import pacsValid from "../../../examples/sepa/pacs008-valid.xml?raw";
import pacsProblems from "../../../examples/sepa/pacs008-problems.xml?raw";
import painValid from "../../../examples/sepa/pain001-valid.xml?raw";

const SAMPLES = [
  { id: "pacs-valid", label: "pacs.008 valid", xml: pacsValid },
  { id: "pacs-problems", label: "pacs.008 with problems", xml: pacsProblems },
  { id: "pain-valid", label: "pain.001 valid", xml: painValid },
];

async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
  return data;
}

export default function SepaCheckPanel({ api }) {
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
      setResult(await post(`${api}/checks/sepa-sct`, { xml, enforce_unstructured_address_removal: enforce }));
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const parseFailed = result && result.kind !== "sepa_sct_check";

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> EPC SEPA CREDIT TRANSFER</div>
        <h1>SEPA check</h1>
        <p>Checks a pacs.008 or pain.001 against the EPC 2025 SCT implementation guidelines: euro amounts, SLEV, IBAN and BIC, the Latin character set, remittance and address rules. No schema file and no model needed.</p>
      </div>
      <IdentifierCheck api={api} />
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">MESSAGE INPUT</div><h3>pacs.008 or pain.001</h3></div><span className="local-tag"><span className="status-dot green" />DETERMINISTIC</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="sepa-xml">XML document</label>
            <div className="editor-toolbar-actions">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setXml(sample.xml); reset(); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="sepa-xml" className="code-editor" value={xml} onChange={(event) => { setXml(event.target.value); reset(); }} placeholder="Paste a synthetic SEPA credit transfer, or load a sample above." spellCheck="false" required />
          <label className="check-option"><input type="checkbox" checked={enforce} onChange={(event) => { setEnforce(event.target.checked); reset(); }} /> Treat unstructured addresses as errors (simulate the EPC end date)</label>
          <button className="button-primary submit-button" type="submit" disabled={loading || !xml.trim()}>{loading ? "Checking…" : "Check SEPA rules"}<span aria-hidden="true">→</span></button>
          <p className="form-footnote">Covers EPC usage rules only. Your bank or clearing house may add its own rules.</p>
        </form>
        <aside className="result-column">
          <div className={`surface-card result-card ${result && !parseFailed ? (result.compliant ? "result-valid" : "result-invalid") : ""}`} aria-live="polite">
            <div className="eyebrow">CHECK RESULT</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">€</div><h3>Load a sample to start</h3><p>“pacs.008 with problems” breaks more than a dozen EPC rules: USD amount, SHAR, a bad IBAN checksum, a missing debtor address for a Swiss agent…</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Check unavailable</h3><p>{error}</p></div>}
            {parseFailed && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>{result.kind === "malformed_xml" ? "Malformed XML" : "Unsupported XML"}</h3>{result.errors.map((item, index) => <div className="diagnostic" key={index}><strong>{item.code}</strong><p>{item.message}</p></div>)}</div>}
            {result && !parseFailed && <SepaReport result={result} />}
          </div>
          <div className="notice-card"><span className="notice-mark">i</span><div><strong>Address end date deferred</strong><p>The EPC planned to stop unstructured addresses in November 2026, then delayed it in September 2026 without a new date. <a href={result?.unstructured_address_end?.source_url || "https://www.europeanpaymentscouncil.eu/document-library/rulebooks/2025-sepa-credit-transfer-rulebook-version-11"} target="_blank" rel="noreferrer">EPC guidance ↗</a></p></div></div>
        </aside>
      </div>
    </section>
  );
}

function FindingList({ findings }) {
  return findings.map((finding, index) => (
    <div className={`diagnostic severity-${finding.severity}`} key={`${finding.rule}-${index}`}>
      <strong>{finding.severity.toUpperCase()} · {finding.rule}</strong>
      <p>{finding.message}</p>
      {finding.suggestion && <p className="finding-fix">Fix: {finding.suggestion}</p>}
      {finding.xpath && <small>{finding.xpath}</small>}
    </div>
  ));
}

function SepaReport({ result }) {
  if (!result.in_scope) {
    return <div className="result-message"><span className="result-symbol">–</span><h3>Not a SEPA credit transfer</h3><p>Only pacs.008 (FIToFICstmrCdtTrf) and pain.001 (CstmrCdtTrfInitn) messages are checked.</p></div>;
  }
  const { summary } = result;
  return (
    <div className="result-message">
      <span className="result-symbol">{result.compliant ? "✓" : "!"}</span>
      <h3>{result.compliant ? "Meets EPC SCT rules" : "Breaks EPC SCT rules"}</h3>
      <p><code>{result.message_id || result.message_type}</code> · {summary.transactions} transaction{summary.transactions === 1 ? "" : "s"} · {summary.errors} error{summary.errors === 1 ? "" : "s"} · {summary.warnings} warning{summary.warnings === 1 ? "" : "s"}</p>
      {result.message_findings.length > 0 && <div className="address-block"><div className="address-heading"><strong>Message</strong></div><FindingList findings={result.message_findings} /></div>}
      {result.transactions.map((transaction) => (
        <div className="address-block" key={transaction.xpath}>
          <div className="address-heading"><strong>{transaction.end_to_end_id || "Transaction"}</strong>{transaction.non_eea_agent && <span className="format-badge format-hybrid">NON-EEA AGENT</span>}</div>
          {transaction.findings.length === 0 && <p className="address-ok">No findings.</p>}
          <FindingList findings={transaction.findings} />
        </div>
      ))}
    </div>
  );
}

function IdentifierCheck({ api }) {
  const [value, setValue] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function check(kind) {
    setResult(null);
    setError("");
    try {
      setResult({ kind, ...(await post(`${api}/identifiers/${kind}`, { value })) });
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    }
  }

  return (
    <div className="surface-card identifier-card">
      <label className="field-label" htmlFor="identifier">Quick IBAN / BIC check</label>
      <div className="search-input-row">
        <input id="identifier" value={value} onChange={(event) => { setValue(event.target.value); setResult(null); setError(""); }} placeholder="DE89 3704 0044 0532 0130 00 or DEUTDEFF" maxLength={100} />
        <button type="button" className="button-secondary" disabled={!value.trim()} onClick={() => check("iban")}>IBAN</button>
        <button type="button" className="button-secondary" disabled={!value.trim()} onClick={() => check("bic")}>BIC</button>
      </div>
      {error && <div className="field-note error-note">{error}</div>}
      {result && (
        <div className={`identifier-result ${result.valid ? "identifier-valid" : "identifier-invalid"}`} aria-live="polite">
          <strong>{result.valid ? "✓ Valid format" : "✕ Invalid"}</strong>
          {result.kind === "iban" && result.country_name && <span>{result.country_name}{result.sepa ? " · SEPA" : " · outside SEPA"} · <code>{result.print_format}</code></span>}
          {result.kind === "bic" && result.country && <span>Institution {result.party_prefix} · country {result.country}{result.sepa ? " (SEPA)" : ""} · branch {result.branch}{result.is_test_bic ? " · test BIC" : ""}</span>}
          {result.errors.map((item) => <span key={item.code}>{item.code}: {item.message}</span>)}
          <small>{result.limitation}</small>
        </div>
      )}
    </div>
  );
}
