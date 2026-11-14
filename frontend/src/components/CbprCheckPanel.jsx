import { useState } from "react";
import cbprValid from "../../../examples/cbpr/pacs008-valid.xml?raw";
import cbprProblems from "../../../examples/cbpr/pacs008-problems.xml?raw";
import addressProblems from "../../../examples/postal-address/problems.xml?raw";

const SAMPLES = [
  { id: "valid", label: "Valid pacs.008", xml: cbprValid },
  { id: "problems", label: "With problems", xml: cbprProblems },
  { id: "addresses", label: "Address problems", xml: addressProblems },
];

const FORMAT_LABELS = { structured: "STRUCTURED", hybrid: "HYBRID", unstructured: "UNSTRUCTURED" };

async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
  return data;
}

export default function CbprCheckPanel({ api }) {
  const [xml, setXml] = useState("");
  const [enforce, setEnforce] = useState(false);
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function reset() {
    setResult(null);
    setSummary(null);
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    reset();
    setLoading(true);
    try {
      const [check, overview] = await Promise.all([
        post(`${api}/checks/cbpr-pacs008`, { xml, enforce_unstructured_removal: enforce }),
        post(`${api}/summaries/payment`, { xml }),
      ]);
      setResult(check);
      setSummary(overview);
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const parseFailed = result && result.kind !== "cbpr_pacs008_check";

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> CBPR+ USAGE RULES</div>
        <h1>CBPR+ check</h1>
        <p>Checks a cross-border pacs.008 against CBPR+ rules an XSD cannot enforce: UETR, one transaction per message, charges, ISO 4217 decimals, IBAN and BIC, characters and postal addresses. It also shows who pays whom through which banks. No schema file and no model needed.</p>
      </div>
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">MESSAGE INPUT</div><h3>pacs.008</h3></div><span className="local-tag"><span className="status-dot green" />DETERMINISTIC</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="cbpr-xml">XML document</label>
            <div className="editor-toolbar-actions">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setXml(sample.xml); reset(); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="cbpr-xml" className="code-editor" value={xml} onChange={(event) => { setXml(event.target.value); reset(); }} placeholder="Paste a synthetic pacs.008, or load a sample above." spellCheck="false" required />
          <label className="check-option"><input type="checkbox" checked={enforce} onChange={(event) => { setEnforce(event.target.checked); reset(); }} /> Treat unstructured addresses as errors (simulate the removal deadline)</label>
          <button className="button-primary submit-button" type="submit" disabled={loading || !xml.trim()}>{loading ? "Checking…" : "Check CBPR+ rules"}<span aria-hidden="true">→</span></button>
          <p className="form-footnote">Covers CBPR+ usage rules only. Your correspondent banks may add their own.</p>
        </form>
        <aside className="result-column">
          {summary && summary.kind === "payment_summary" && summary.transactions.length > 0 && <PaymentRoute summary={summary} />}
          <div className={`surface-card result-card ${result && !parseFailed ? (result.compliant ? "result-valid" : "result-invalid") : ""}`} aria-live="polite">
            <div className="eyebrow">CHECK RESULT</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">⇄</div><h3>Load a sample to start</h3><p>“With problems” has two transactions, an upper-case UETR, JPY with decimals, missing charges information, SLEV and a bad IBAN.</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Check unavailable</h3><p>{error}</p></div>}
            {parseFailed && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>{result.kind === "malformed_xml" ? "Malformed XML" : "Unsupported XML"}</h3>{result.errors.map((item, index) => <div className="diagnostic" key={index}><strong>{item.code}</strong><p>{item.message}</p></div>)}</div>}
            {result && !parseFailed && <CbprReport result={result} />}
          </div>
          <div className="notice-card"><span className="notice-mark">i</span><div><strong>Address deadline deferred</strong><p>Swift planned to remove unstructured addresses on 14 November 2026, then deferred it on 27 August 2026; a new date is due by December. <a href="https://www.swift.com/insights/news/swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages" target="_blank" rel="noreferrer">Swift announcement ↗</a></p></div></div>
        </aside>
      </div>
    </section>
  );
}

function PaymentRoute({ summary }) {
  const transaction = summary.transactions[0];
  const amount = transaction.interbank_settlement_amount || transaction.instructed_amount;
  return (
    <div className="surface-card route-card">
      <div className="eyebrow">PAYMENT SUMMARY</div>
      <p className="route-amount">{amount ? `${amount.value} ${amount.currency}` : "No amount"}{transaction.charge_bearer && <span> · charges {transaction.charge_bearer}</span>}{transaction.settlement_date && <span> · {transaction.settlement_date}</span>}</p>
      <ol className="route-list">
        <li><strong>{transaction.debtor?.name || "Debtor"}</strong><small>{transaction.debtor_account || "no account"}{transaction.debtor?.country ? ` · ${transaction.debtor.country}` : ""}</small></li>
        {transaction.agent_chain.filter((agent) => !["InstgAgt", "InstdAgt"].includes(agent.role)).map((agent) => <li key={agent.role}><strong>{agent.bic || agent.name || agent.clearing_member_id || "Agent"}</strong><small>{agent.label}</small></li>)}
        <li><strong>{transaction.creditor?.name || "Creditor"}</strong><small>{transaction.creditor_account || "no account"}{transaction.creditor?.country ? ` · ${transaction.creditor.country}` : ""}</small></li>
      </ol>
      {transaction.uetr && <small className="route-meta">UETR {transaction.uetr}</small>}
      {summary.transactions.length > 1 && <small className="route-meta">+ {summary.transactions.length - 1} more transaction(s)</small>}
    </div>
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

function CbprReport({ result }) {
  if (!result.in_scope) {
    return <div className="result-message"><span className="result-symbol">–</span><h3>Not a pacs.008</h3><p>This check covers FI-to-FI customer credit transfers (FIToFICstmrCdtTrf).</p></div>;
  }
  const { summary } = result;
  const addresses = result.postal_addresses?.addresses || [];
  return (
    <div className="result-message">
      <span className="result-symbol">{result.compliant ? "✓" : "!"}</span>
      <h3>{result.compliant ? "Meets CBPR+ rules" : "Breaks CBPR+ rules"}</h3>
      <p><code>{result.message_id || "pacs.008"}</code> · {summary.errors} error{summary.errors === 1 ? "" : "s"} · {summary.warnings} warning{summary.warnings === 1 ? "" : "s"}</p>
      {result.message_findings.length > 0 && <div className="address-block"><div className="address-heading"><strong>Message</strong></div><FindingList findings={result.message_findings} /></div>}
      {result.transactions.map((transaction) => (
        <div className="address-block" key={transaction.xpath}>
          <div className="address-heading"><strong>{transaction.end_to_end_id || "Transaction"}</strong></div>
          {transaction.findings.length === 0 && <p className="address-ok">No findings.</p>}
          <FindingList findings={transaction.findings} />
        </div>
      ))}
      {addresses.map((address) => (
        <div className="address-block" key={address.xpath}>
          <div className="address-heading"><strong>{address.role_label} address</strong><span className={`format-badge format-${address.format}`}>{FORMAT_LABELS[address.format]}</span></div>
          {address.findings.length === 0 && <p className="address-ok">No findings.</p>}
          <FindingList findings={address.findings} />
        </div>
      ))}
    </div>
  );
}
