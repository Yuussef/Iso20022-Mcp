import { useState } from "react";
import statement from "../../../examples/read/camt053-statement.xml?raw";
import cbprReject from "../../../examples/status/pacs002-cbpr-reject.xml?raw";
import cbprPayment from "../../../examples/cbpr/pacs008-valid.xml?raw";

const SAMPLES = [
  { id: "camt053", label: "camt.053 statement", xml: statement },
  { id: "pacs002", label: "pacs.002 status", xml: cbprReject },
  { id: "pacs008", label: "pacs.008 payment", xml: cbprPayment },
];

export default function ReaderPanel({ api }) {
  const [xml, setXml] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setResult(null);
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${api}/read`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ xml }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
      setResult(data);
    } catch (requestError) {
      setError(requestError.message || "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  const failed = result && result.kind !== "message_reading";

  return (
    <section className="tool-page">
      <div className="tool-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> ANY ISO 20022 MESSAGE</div>
        <h1>Read a message</h1>
        <p>Paste any ISO 20022 message (pacs, pain, camt statements and notifications, head, admi) to see what it is, its references, amounts, parties, codes with their meaning, statement entries and balances. It restates the message; it does not judge it.</p>
      </div>
      <div className="tool-layout">
        <form className="surface-card editor-card" onSubmit={submit}>
          <div className="card-heading"><div><div className="eyebrow">MESSAGE INPUT</div><h3>Any ISO 20022 XML</h3></div><span className="local-tag"><span className="status-dot green" />READ ONLY</span></div>
          <div className="editor-toolbar">
            <label className="field-label" htmlFor="reader-xml">XML document</label>
            <div className="editor-toolbar-actions">
              {SAMPLES.map((sample) => <button type="button" className="upload-button" key={sample.id} onClick={() => { setXml(sample.xml); setResult(null); setError(""); }}>{sample.label}</button>)}
            </div>
          </div>
          <textarea id="reader-xml" className="code-editor" value={xml} onChange={(event) => { setXml(event.target.value); setResult(null); setError(""); }} placeholder="Paste a synthetic ISO 20022 message, or load a sample above." spellCheck="false" required />
          <button className="button-primary submit-button" type="submit" disabled={loading || !xml.trim()}>{loading ? "Reading…" : "Read message"}<span aria-hidden="true">→</span></button>
        </form>
        <aside className="result-column">
          <div className="surface-card result-card" aria-live="polite">
            <div className="eyebrow">WHAT IT CONTAINS</div>
            {!result && !error && <div className="result-empty"><div className="result-symbol">≡</div><h3>Load a sample to start</h3><p>The camt.053 sample shows entries, credit and debit totals and balances.</p></div>}
            {error && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>Cannot read</h3><p>{error}</p></div>}
            {failed && <div className="result-message"><span className="result-symbol error-symbol">!</span><h3>{result.kind === "malformed_xml" ? "Malformed XML" : "Unsupported XML"}</h3>{result.errors.map((item, index) => <div className="diagnostic" key={index}><strong>{item.code}</strong><p>{item.message}</p></div>)}</div>}
            {result && !failed && <Reading result={result} />}
          </div>
        </aside>
      </div>
    </section>
  );
}

function Reading({ result }) {
  const references = Object.entries(result.references).filter(([, values]) => values.length);
  return (
    <div className="result-message">
      <span className="result-symbol">≡</span>
      <h3>{result.message_name || "Unknown message"}</h3>
      <p><code>{result.message_id || result.root_element}</code>{result.purpose && ` · ${result.purpose}`}</p>
      {result.group_header && <Block title="Group header" lines={[result.group_header.message_identification && `Message ${result.group_header.message_identification}`, result.group_header.created && `Created ${result.group_header.created}`, result.group_header.number_of_transactions && `${result.group_header.number_of_transactions} transaction(s)`]} />}
      {references.length > 0 && <Block title="References" lines={references.map(([key, values]) => `${key.replaceAll("_", " ")}: ${values.slice(0, 3).join(", ")}${values.length > 3 ? "…" : ""}`)} />}
      {(result.parties.length > 0 || result.agents.length > 0) && <Block title="Parties and banks" lines={[...result.parties.map((party) => `${party.role}: ${party.name || party.bic || "?"}${party.country ? ` (${party.country})` : ""}`), ...result.agents.map((agent) => `${agent.role}: ${agent.bic || agent.name || "?"}`)].slice(0, 10)} />}
      {result.codes.length > 0 && <Block title="Codes" lines={result.codes.map((code) => `${code.element} ${code.code}: ${code.meaning || "not in the ISO list"}`)} />}
      {result.entries && <Block title={`Entries (${result.entries.count})`} lines={[...Object.entries(result.entries.totals).map(([currency, totals]) => `${currency}: credits ${totals.credits}, debits ${totals.debits}`), ...result.entries.items.slice(0, 5).map((entry) => `${entry.credit_debit} ${entry.amount} ${entry.currency} · ${entry.booking_date || "?"}${entry.remittance ? ` · ${entry.remittance}` : ""}`)]} />}
      {result.balances.length > 0 && <Block title="Balances" lines={result.balances.map((balance) => `${balance.type}: ${balance.amount} ${balance.currency} ${balance.credit_debit} on ${balance.date}`)} />}
      {result.amounts.length > 0 && !result.entries && <Block title={`Amounts (${result.amounts.length})`} lines={result.amounts.slice(0, 6).map((amount) => `${amount.element}: ${amount.value} ${amount.currency}`)} />}
      {result.suggested_tools.length > 0 && <Block title="Check it with" lines={result.suggested_tools} />}
    </div>
  );
}

function Block({ title, lines }) {
  const shown = lines.filter(Boolean);
  if (!shown.length) return null;
  return (
    <div className="address-block">
      <div className="address-heading"><strong>{title}</strong></div>
      <ul className="reader-list">{shown.map((line, index) => <li key={index}>{line}</li>)}</ul>
    </div>
  );
}
