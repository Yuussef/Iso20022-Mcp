export default function Dashboard({ health, messages, configured, onNavigate }) {
  const availableCount = messages.filter((item) => item.available).length;
  return (
    <>
      <section className="hero-row">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> PAYMENT ENGINEERING TOOLKIT</div>
          <h1>A valid XSD is not<br /><span>an accepted payment.</span></h1>
          <p className="hero-copy">Check SEPA Credit Transfers against the EPC rules and cross-border pacs.008 against CBPR+, fix postal addresses, validate IBANs and BICs, and see what an MT103 loses on its way to ISO 20022. Deterministic, sourced and also available to AI agents over MCP. Use synthetic data only.</p>
          <div className="hero-actions">
            <button className="button-primary" onClick={() => onNavigate("sepa")}>Check a SEPA payment <span aria-hidden="true">→</span></button>
            <button className="button-secondary" onClick={() => onNavigate("cbpr")}>Check a CBPR+ pacs.008</button>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" /><div className="orbit orbit-two" />
          <div className="art-center"><span>ISO</span><strong>20022</strong></div>
          <span className="art-chip chip-top">SEPA · CBPR+</span><span className="art-chip chip-bottom">MT103 → pacs.008</span>
          <span className="art-node node-one" /><span className="art-node node-two" />
        </div>
      </section>

      {!configured && (
        <section className="setup-banner" aria-label="Schema setup notice">
          <span className="banner-icon" aria-hidden="true">i</span>
          <div><strong>XSD validation uses a synthetic demo schema</strong><p>The SEPA, CBPR+, address and MT103 checks need no schema. To validate against an official ISO 20022 XSD, add a permitted file and register its exact message version.</p></div>
          <button className="text-button" onClick={() => onNavigate("validate")}>XSD setup <span aria-hidden="true">→</span></button>
        </section>
      )}

      <section className="section-heading"><div><div className="eyebrow">YOUR WORKSPACE</div><h2>At a glance</h2></div><span className="live-label"><span className={`status-dot ${health === "online" ? "green" : "muted"}`} />{health === "online" ? "All systems ready" : "Connecting to API"}</span></section>
      <section className="stat-grid" aria-label="Workspace status">
        <article className="stat-card"><div className="stat-top"><span className="stat-icon purple">€</span><span className="stat-caption">RULE CHECKS</span></div><strong className="stat-number stat-word">SEPA · CBPR+</strong><span className="stat-detail">EPC 2025 SCT rules, CBPR+ pacs.008, postal addresses, IBAN/BIC</span></article>
        <article className="stat-card"><div className="stat-top"><span className="stat-icon blue">⌕</span><span className="stat-caption">SOURCED REFERENCE DATA</span></div><strong className="stat-number stat-word">EPC · Swift · SIX</strong><span className="stat-detail">IBAN Registry, SEPA countries, ISO 4217; every rule cites its source</span></article>
        <article className="stat-card"><div className="stat-top"><span className="stat-icon mint">✳</span><span className="stat-caption">FOR AI AGENTS</span></div><strong className="stat-number stat-word">MCP server</strong><span className="stat-detail">The same checks as tools for Claude and other agents; {availableCount} XSD {availableCount === 1 ? "schema" : "schemas"} registered</span></article>
      </section>

      <section className="bottom-grid">
        <article className="surface-card focus-card"><div className="card-heading"><div><div className="eyebrow">START HERE</div><h3>Try it with the samples</h3></div><span className="step-count">01 — 03</span></div>
          <div className="workflow-list">
            <button type="button" className="workflow-item workflow-link" onClick={() => onNavigate("sepa")}><span className="workflow-number">1</span><div><strong>Check a SEPA credit transfer</strong><p>Load “pacs.008 with problems”: USD, SHAR, a bad IBAN and a Swiss bank without a debtor address.</p></div><span className="workflow-state">OPEN →</span></button>
            <button type="button" className="workflow-item workflow-link" onClick={() => onNavigate("cbpr")}><span className="workflow-number">2</span><div><strong>Check a cross-border pacs.008</strong><p>See the bank route, then UETR, charges and JPY decimal findings.</p></div><span className="workflow-state">OPEN →</span></button>
            <button type="button" className="workflow-item workflow-link" onClick={() => onNavigate("mt103")}><span className="workflow-number">3</span><div><strong>Convert a legacy MT103</strong><p>See, field by field, what is missing for CBPR+.</p></div><span className="workflow-state">OPEN →</span></button>
          </div>
        </article>
        <article className="surface-card registry-card"><div className="card-heading"><div><div className="eyebrow">LOCAL SOURCES</div><h3>Message registry</h3></div><span className="registry-count">{messages.length.toString().padStart(2, "0")}</span></div>
          {messages.length ? <div className="registry-list">{messages.map((message) => <div className="registry-row" key={message.message_id}><span className="schema-icon">XML</span><div><strong>{message.message_id}</strong><small>{message.title}</small></div><span className={`registry-status ${message.available ? "ready" : "missing"}`}>{message.available ? "READY" : "XSD MISSING"}</span></div>)}</div> : <div className="empty-registry"><span className="empty-icon">⌁</span><strong>Nothing registered yet</strong><p>When you add a local schema, its exact version will appear here.</p><button className="text-button" onClick={() => onNavigate("validate")}>Configure a schema →</button></div>}
        </article>
      </section>
    </>
  );
}
