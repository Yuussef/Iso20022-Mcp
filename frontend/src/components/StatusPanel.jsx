import { useState } from "react";
import sepaReject from "../../../examples/status/pacs002-sepa-reject.xml?raw";
import sepaReturn from "../../../examples/status/pacs004-sepa-return.xml?raw";
import cbprReject from "../../../examples/status/pacs002-cbpr-reject.xml?raw";
import painPartial from "../../../examples/status/pain002-partial.xml?raw";
import sepaProblems from "../../../examples/status/pacs002-sepa-problems.xml?raw";
import sepaPayment from "../../../examples/sepa/pacs008-valid.xml?raw";
import cbprPayment from "../../../examples/cbpr/pacs008-valid.xml?raw";
import painPayment from "../../../examples/sepa/pain001-valid.xml?raw";

const SAMPLES = [
  { id: "sepa-reject", label: "SEPA reject (AC01)", xml: sepaReject, original: sepaPayment },
  { id: "sepa-return", label: "SEPA return (AC04)", xml: sepaReturn, original: sepaPayment },
  { id: "cbpr-reject", label: "CBPR+ reject", xml: cbprReject, original: cbprPayment },
  { id: "pain002", label: "pain.002 partial", xml: painPartial, original: painPayment },
  { id: "problems", label: "SEPA reject with problems", xml: sepaProblems, original: "" },
];

export default function StatusPanel({ api }) {
  const [xml, setXml] = useState("");
  const [original, setOriginal] = useState("");
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
      const response = await fetch(`${api}/explain/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ xml, original_xml: original.trim() ? original : null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
      setResult(data);
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const parseFailed = result && result.kind !== "payment_status_explanation";

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> REJECTS · STATUSES · RETURNS</div>
        <h1>Why was it rejected or returned?</h1>
        <p>Paste a pacs.002, pain.002 or pacs.004. Every status and reason code is explained from the official ISO 20022 code lists, SEPA and CBPR+ rules are checked, and with the original payment each status is matched to its transaction.</p>
      </div>
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">STATUS OR RETURN</div><h3>pacs.002 · pain.002 · pacs.004</h3></div><span className="local-tag"><span className="status-dot green" />ISO CODES</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="status-xml">Status report or return</label>
            <div className="editor-toolbar-actions sample-wrap">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setXml(sample.xml); setOriginal(sample.original); reset(); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="status-xml" className="code-editor" value={xml} onChange={(event) => { setXml(event.target.value); reset(); }} placeholder="Paste a synthetic pacs.002, pain.002 or pacs.004, or load a sample above." spellCheck="false" required />
          <label className="field-label original-label" htmlFor="original-xml">Original payment (optional, pacs.008 or pain.001)</label>
          <textarea id="original-xml" className="code-editor original-editor" value={original} onChange={(event) => { setOriginal(event.target.value); reset(); }} placeholder="Paste the original payment to match each status to its transaction." spellCheck="false" />
          <button className="button-primary submit-button" type="submit" disabled={loading || !xml.trim()}>{loading ? "Explaining…" : "Explain"}<span aria-hidden="true">→</span></button>
          <p className="form-footnote">Code meanings come from the ISO 20022 External Code Sets; SEPA reasons from the EPC 2025 guidelines.</p>
        </form>
        <aside className="result-column">
          <div className={`surface-card result-card ${result && !parseFailed && result.in_scope ? (result.compliant ? "result-valid" : "result-invalid") : ""}`} aria-live="polite">
            <div className="eyebrow">EXPLANATION</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">↩</div><h3>Load a sample to start</h3><p>“SEPA return (AC04)” explains a return for a closed account and ties it to the original payment.</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Explanation unavailable</h3><p>{error}</p></div>}
            {parseFailed && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>{result.kind === "malformed_xml" ? "Malformed XML" : "Unsupported XML"}</h3>{result.errors.map((item, index) => <div className="diagnostic" key={index}><strong>{item.code}</strong><p>{item.message}</p></div>)}</div>}
            {result && !parseFailed && <StatusReport result={result} />}
          </div>
        </aside>
      </div>
    </section>
  );
}

function StatusReport({ result }) {
  if (!result.in_scope) {
    return <div className="result-message"><span className="result-symbol">–</span><h3>Not a status or return</h3><p>{result.note}</p></div>;
  }
  const { summary } = result;
  const groupStatus = result.group?.status;
  return (
    <div className="result-message">
      <span className="result-symbol">{result.compliant ? "✓" : "!"}</span>
      <h3>{summary.returned ? `${summary.returned} payment(s) returned` : summary.rejected ? `${summary.rejected} payment(s) rejected` : "Status report"}</h3>
      <p><code>{result.message_id || result.message_type}</code> · {result.scheme.toUpperCase()} rules · {summary.errors} error{summary.errors === 1 ? "" : "s"} · {summary.warnings} warning{summary.warnings === 1 ? "" : "s"}{result.match && ` · ${result.match.matched}/${summary.transactions} matched`}</p>
      {groupStatus && <div className="address-block"><div className="address-heading"><strong>Group status</strong><span className="format-badge format-hybrid">{groupStatus.code}</span></div><p className="address-ok">{groupStatus.meaning || "Not an ISO code"}</p></div>}
      {result.message_findings.map((finding, index) => <Finding finding={finding} key={`m-${index}`} />)}
      {result.transactions.map((transaction) => (
        <div className="address-block" key={transaction.xpath}>
          <div className="address-heading">
            <strong>{transaction.original.uetr || transaction.original.end_to_end_id || transaction.original.transaction_id || "Transaction"}</strong>
            {transaction.status && <span className={`format-badge ${transaction.status.code === "RJCT" || transaction.status.code === "RETURNED" ? "format-unstructured" : "format-structured"}`}>{transaction.status.code}</span>}
          </div>
          {transaction.status && <p className="address-ok">{transaction.status.meaning || "Not an ISO status code"}</p>}
          {transaction.reasons.map((reason, index) => (
            <div className="diagnostic reason-card" key={index}>
              <strong>REASON {reason.code || reason.proprietary || "?"}</strong>
              <p>{reason.meaning || "Not in the ISO code list"}</p>
              {reason.scheme_meaning && <p className="finding-fix">SEPA: {reason.scheme_meaning}</p>}
              {reason.additional_info.map((info, infoIndex) => <small key={infoIndex}>{info}</small>)}
              {reason.originator && <small>Raised by {reason.originator}</small>}
            </div>
          ))}
          {transaction.returned_amount && <p className="address-ok">Returned {transaction.returned_amount.value} {transaction.returned_amount.currency}{transaction.original_amount ? ` of ${transaction.original_amount.value} ${transaction.original_amount.currency}` : ""}</p>}
          {transaction.match && <p className="address-ok">Original payment: {transaction.match.matched_by ? `matched by ${transaction.match.matched_by.replaceAll("_", " ")}` : "not found"}</p>}
          {transaction.findings.map((finding, index) => <Finding finding={finding} key={index} />)}
        </div>
      ))}
    </div>
  );
}

function Finding({ finding }) {
  return (
    <div className={`diagnostic severity-${finding.severity}`}>
      <strong>{finding.severity.toUpperCase()} · {finding.rule}</strong>
      <p>{finding.message}</p>
      {finding.suggestion && <p className="finding-fix">Fix: {finding.suggestion}</p>}
      {finding.xpath && <small>{finding.xpath}</small>}
    </div>
  );
}
