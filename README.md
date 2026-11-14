# PayDoc AI

[![CI](https://github.com/Yuussef/Iso20022-Mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Yuussef/Iso20022-Mcp/actions/workflows/ci.yml)

*PayDoc AI is the product name; the repository is [Iso20022-Mcp](https://github.com/Yuussef/Iso20022-Mcp).*

**A local-first ISO 20022 developer workbench built with FastAPI and React.** It validates XML against an explicitly selected local XSD, checks SEPA Credit Transfers against the EPC rules and postal addresses against the CBPR+ rules that an XSD cannot enforce, validates IBANs and BICs offline, searches a small local reference corpus, and exposes the same operations as MCP tools. An optional AWS Bedrock client can call those MCP tools before answering.

> This is a portfolio project, not a payment processor, compliance product, or banking system. Use synthetic XML only.

## Current status

| Capability | Status |
| --- | --- |
| FastAPI health and schema-registry endpoints | Implemented |
| Secure XML parsing and local XSD validation | Implemented; includes a synthetic demo XSD, not an official ISO 20022 schema |
| SEPA Credit Transfer check (EPC 2025 rules, pacs.008 and pain.001) | Implemented; needs no XSD; synthetic samples included |
| IBAN (ISO 13616 registry + mod-97) and BIC (ISO 9362) validation | Implemented; offline, format only |
| CBPR+ postal address check (structured / hybrid / unstructured) | Implemented; needs no XSD; synthetic pacs.008 samples included |
| Local source manifest and keyword search with provenance links | Implemented; starter corpus contains three original project notes |
| React dashboard, validator form, address check, XML file upload, search UI | Implemented |
| MCP server exposing shared domain operations over stdio | Implemented; install the optional `ai` dependencies |
| Bedrock Converse client invoking MCP tools and returning sources | Implemented; requires AWS credentials and a configured model with tool use |
| Starter evaluation cases | `data/evaluations/starter.jsonl` runs in the test suite; measured metrics are next |

The registry includes one synthetic demo schema so you can exercise the validator; it is not an official ISO 20022 schema. No official ISO message version is bundled. Add an approved XSD and register its exact message ID before validating real ISO message structures. The app never downloads a schema or guesses a version. The starter search is lexical keyword matching, not embeddings or semantic RAG. The optional AI path is disabled until configured and needs the `ai` dependency extra.

## Why this project

Payment developers need to inspect message structure, understand validation errors, and find the documentation that applies to a particular message version. PayDoc AI demonstrates how a senior software engineer can combine backend engineering, payment-domain experience, MCP, and grounded AI while keeping validation deterministic.

## Features

- **Version-explicit validation:** choose a registered message ID such as `pacs.008.001.08`; the server validates against its local XSD.
- **Structured diagnostics:** return schema/parser error code, message, line, column, and XPath when available.
- **SEPA Credit Transfer check:** apply the EPC 2025 SCT rules that an XSD cannot enforce, such as euro-only amounts, SLEV, IBAN-only accounts and the non-EEA debtor address rule (see [below](#sepa-credit-transfer-check)).
- **IBAN and BIC validation:** national length and structure from the Swift IBAN Registry, mod-97 check digits, ISO 9362 BIC format, test BICs and SEPA membership. Offline, so it proves the format, not that the account exists.
- **CBPR+ postal address check:** classify every `PstlAdr` as structured, hybrid or unstructured and report rule violations with severity, XPath and a suggested fix (see [below](#cbpr-postal-address-check)).
- **Safe XML parsing:** disable network access, entity resolution, and DTD loading; reject any DOCTYPE; cap XML input length.
- **Source-backed lookup:** search local Markdown references and return a source ID, excerpt, and provenance link.
- **MCP tools:** list versions, validate a message, check SEPA credit transfers and postal addresses, validate IBANs and BICs, search local documents, and look up evidence related to an error.
- **Optional AI assistant:** Bedrock receives tool definitions through the MCP SDK and surfaces returned sources; it does not decide whether XML passes the XSD.
- **React + FastAPI:** a responsive dashboard, validator, knowledge search, and assistant call the real API.

XSD validation only checks the constraints represented by the chosen schema. It does not prove compliance with scheme-specific, community, or bank usage guidelines. ISO 20022 itself notes that implementation requirements depend on the community using a message. See the [official FAQ](https://www.iso20022.org/faq).

## SEPA Credit Transfer check

`POST /api/v1/checks/sepa-sct` (MCP tool `check_sepa_sct`) checks a pacs.008 (interbank) or pain.001 (customer to bank) against the EPC 2025 SCT implementation guidelines. It needs no XSD.

| Rule | Severity | What it catches |
| --- | --- | --- |
| `SEPA_CURRENCY`, `SEPA_AMOUNT_RANGE`, `SEPA_AMOUNT_DECIMALS` | error | Non-euro amount, outside 0.01 – 999 999 999.99, more than two decimals |
| `SEPA_CHARGE_BEARER` | error | Charge bearer other than `SLEV` (mandatory in pacs.008) |
| `SEPA_SERVICE_LEVEL`, `SEPA_SERVICE_LEVEL_MISSING` | error | Service level other than `SEPA`, or none |
| `SEPA_ACCOUNT_NOT_IBAN`, `SEPA_IBAN_*`, `SEPA_IBAN_OUTSIDE_SEPA` | error | Account not an IBAN, invalid IBAN, or IBAN country outside SEPA |
| `SEPA_AGENT_NOT_BIC`, `SEPA_BIC_*` | error | Agent identified by anything other than a valid `BICFI` |
| `SEPA_REFERENCE_FORMAT` | error | Identifier outside the Latin set, starting or ending with `/`, or containing `//` |
| `SEPA_CHARACTER_SET` | warning | Names, remittance or address lines outside the Latin set (allowed only by agreement) |
| `SEPA_NAME_*`, `SEPA_PARTY_MISSING` | error | Missing debtor or creditor, or name over 70 characters |
| `SEPA_REMITTANCE_*` | error | Both structured and unstructured, repeated, or over 140 characters |
| `SEPA_ADDRESS_*` | error / warning | EPC structured, hybrid and unstructured address rules; unstructured is a warning while the end date is deferred |
| `SEPA_DEBTOR_ADDRESS_REQUIRED`, `SEPA_ADDRESS_COUNTRY_REQUIRED` | error | Debtor address and country missing when an agent is in a non-EEA SEPA country (for example CH or GB) |

**Address end date.** The EPC planned to stop unstructured addresses in November 2026. In September 2026 it [delayed that end date](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-09/EPC153-22%20v2.2%20EPC%20guidance%20document%20-%20Provision%20of%20Addresses%20under%20the%20EPC%20Payment%20Schemes.pdf) for all five EPC schemes without setting a new one. Set `enforce_unstructured_address_removal` to simulate it.

Sources: the [EPC SCT rulebook and implementation guidelines](https://www.europeanpaymentscouncil.eu/what-we-do/epc-payment-schemes/sepa-credit-transfer-sct/sepa-credit-transfer-rulebook-and) (EPC115-06 and EPC132-08, 2025 v1.0), [EPC409-09 v8.0](https://www.europeanpaymentscouncil.eu/document-library/other/epc-list-sepa-scheme-countries) for SEPA countries, and the [Swift IBAN Registry](https://www.swift.com/standards/data-standards/iban-international-bank-account-number) in [`data/reference/`](data/reference). The check covers EPC usage rules only; a bank or clearing house may add its own.

`POST /api/v1/identifiers/iban` and `/identifiers/bic` (MCP tools `validate_iban`, `validate_bic`) validate a single identifier. Synthetic samples are in [`examples/sepa/`](examples/sepa).

## CBPR+ postal address check

The ISO 20022 XSD accepts addresses that CBPR+ rejects. `POST /api/v1/checks/postal-address` (and the MCP tool `check_cbpr_postal_addresses`) inspects every `PstlAdr` in a message and needs no schema file.

| Rule | Severity | What it catches |
| --- | --- | --- |
| `CBPR_ADDR_UNSTRUCTURED` | warning (error with `enforce_unstructured_removal`) | Address made only of `AdrLine` free text |
| `CBPR_ADDR_TOWN_MISSING` / `CBPR_ADDR_COUNTRY_MISSING` | error | Structured or hybrid address without `TwnNm` or `Ctry` |
| `CBPR_ADDR_TOO_MANY_LINES` | error | Hybrid address with more than two `AdrLine` |
| `CBPR_ADDR_TOO_LONG` | error | Element longer than its CBPR+ limit (`TwnNm` 35, `PstCd` 16, `AdrLine` 70, …) |
| `CBPR_ADDR_COUNTRY_FORMAT` | error | `Ctry` that is not a two-letter upper-case ISO 3166 code |
| `CBPR_ADDR_POSTCODE_IN_TOWN` | warning | Post code mapped into `TwnNm` (for example `75001 Paris`) |
| `CBPR_ADDR_DUPLICATED_IN_LINE` | warning | Hybrid `AdrLine` repeating the town already in `TwnNm` |
| `CBPR_ADDR_AGENT_HAS_BIC` | info | Agent identified by BIC, where the BIC alone is a valid option |

**Deadline status.** Swift planned to remove unstructured addresses from CBPR+ payment messages on 14 November 2026 (SR2026). On 27 August 2026 Swift [deferred all SR2026 payments changes](https://www.swift.com/insights/news/swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages), with new timing to be announced by December 2026. Unstructured addresses are therefore reported as warnings by default; set `enforce_unstructured_removal` to `true` to simulate the removal. Reporting and admin messages (camt.052/053/054/060, camt.025, admi.024) are out of scope, as in the [Swift FAQ](https://www.swift.com/standards/iso-20022/iso-20022-faqs/iso-20022-removal-unstructured-address).

Rules come from the Swift FAQ and news above and from the CBPR+ pacs.008.001.08 usage guideline as published on the [Goldman Sachs developer portal](https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/). They cover postal addresses only, not the rest of the message. Check the current CBPR+ usage guidelines on Swift MyStandards before relying on them.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/checks/postal-address \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{xml: .}' examples/postal-address/problems.xml)"
```

Synthetic samples are in [`examples/postal-address/`](examples/postal-address): `structured.xml`, `hybrid.xml` and `problems.xml`.

## Architecture

```text
React + Vite browser app
  ├── GET  /api/v1/health
  ├── GET  /api/v1/messages
  ├── POST /api/v1/validate ──> local, versioned XSD
  ├── POST /api/v1/checks/sepa-sct ──> EPC SEPA Credit Transfer rules (no XSD needed)
  ├── POST /api/v1/checks/postal-address ──> CBPR+ address rules (no XSD needed)
  ├── POST /api/v1/identifiers/{iban,bic} ──> IBAN Registry + mod-97, ISO 9362
  ├── POST /api/v1/search   ──> local sources + provenance
  └── POST /api/v1/ask      ──> Bedrock Converse ──> MCP client ──> MCP tools

Independent MCP stdio server ──> same Python domain services <── in-memory MCP client + Bedrock Converse
```

The MCP server and HTTP API call the same validation/search service functions in `app/services/`. The Bedrock adapter uses an in-memory MCP client; the server can also run independently over stdio for an MCP host.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 or later and npm
- Git
- One local ISO 20022 XSD for the validation workflow (manual setup below)
- Optional: AWS Bedrock access and credentials for the AI assistant

## Run locally

### 1. Start the API

From the repository root:

```bash
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is at `http://127.0.0.1:8000`; interactive OpenAPI docs are at `http://127.0.0.1:8000/docs`.

To enable the model-backed assistant, install the optional dependencies and configure a Bedrock model that supports Converse tool use:

```bash
uv sync --extra ai
```

Set `BEDROCK_MODEL_ID` and `AWS_REGION` in your local `.env` or shell. The app uses the AWS SDK credential provider chain; follow your approved AWS login flow. Do not include confidential or customer data in assistant prompts.

### 2. Start the React app

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`). The Vite development server proxies `/api` to the FastAPI server on port 8000. `frontend/package-lock.json` is committed; use `npm ci` instead of `npm install` for an exact, reproducible install.

### Windows PowerShell

The same commands work in PowerShell. If you need a local environment file, copy the template with `Copy-Item .env.example .env`. Never add `.env` or credentials to Git.

## Deploy a free demo

The project includes a Render Blueprint for a single FastAPI web service that also serves the built React app. To deploy it, open the [Render Blueprint creation page](https://dashboard.render.com/blueprint/new?repo=https://github.com/Yuussef/Iso20022-Mcp), connect the public GitHub repository, and create the Blueprint. Render builds the frontend and API from `render.yaml` and assigns an `onrender.com` URL.

The free web service can spin down after 15 minutes without requests, so the first visit after inactivity may take a little longer. This is a portfolio demo: do not submit real payment messages, customer information, or confidential documents. No ISO XSD or AWS credentials are included; validation needs a schema you are permitted to use, and the AI assistant stays disabled until configured.

## Add a permitted local ISO 20022 schema

1. To verify the demo, choose `demo.000.001.01` in the validator and click **Load demo XML**. It should pass the bundled synthetic schema. This sample is not ISO 20022.
2. For a real message, visit the [official ISO 20022 Message Definitions catalogue](https://www.iso20022.org/iso-20022-message-definitions) and filter to the Payments domain.
3. Select one message definition and record its **complete identifier and version**. Start with one `pacs.008` version only; do not mix versions in a registry entry.
4. From the relevant message set, obtain the XSD and the smallest useful official reference document. ISO notes that message-set documentation (such as MDRs/MUGs) is provided at message-set level, while each message definition has its own schema.
5. Review the terms for the files. Put the XSD in `data/schemas/` for local use. `.gitignore` excludes downloaded `*.xsd` files by default; do not force-add third-party files unless their terms permit redistribution.
6. Edit `data/schemas/registry.json` with the **actual** identifier and filename from the catalogue:

   ```json
   {
     "pacs.008.001.08": {
       "title": "FinancialInstitutionToFinancialInstitutionCustomerCreditTransferV08",
       "file": "pacs.008.001.08.xsd"
     }
   }
   ```

   These values show the registry shape only. Confirm that the selected official version and downloaded filename really match; update both if they do not.

7. Restart neither API nor UI: the API reads the registry on each request. Refresh the dashboard; the version appears when its local XSD is present.
8. Use synthetic XML for validation. A missing/unregistered XSD returns HTTP `409` with setup guidance; malformed XML returns a deterministic invalid result; XSD failures return diagnostics.

If the local schema package uses XSD imports/includes, keep the required companion schemas beside it and verify that the selected XSD resolves them from the local directory. Do not point the registry to an arbitrary user-uploaded path.

## API examples

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

List registered versions and whether their local XSD is present:

```bash
curl http://127.0.0.1:8000/api/v1/messages
```

Validate a synthetic XML message. This abbreviated sample illustrates the request shape; its expected XSD result depends on the exact schema version you install:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/validate \
  -H "Content-Type: application/json" \
  --data-binary @examples/validate-request.json
```

Search the starter corpus:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search \
  -H "Content-Type: application/json" \
  --data-binary @examples/search-request.json
```

Validation request JSON is in [`examples/validate-request.json`](examples/validate-request.json), and a search request is in [`examples/search-request.json`](examples/search-request.json). Search scores are simple matched-keyword counts; they are not confidence scores.

Ask the optional assistant and launch the independent MCP server:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How should I interpret this validation error?"}'

uv run --extra ai python -m app.mcp_server.server
uv run --extra ai mcp dev app/mcp_server/server.py
```

In PowerShell, use `curl.exe` (not the `curl` alias) and keep each request on one line, for example: `curl.exe -X POST http://127.0.0.1:8000/api/v1/search -H "Content-Type: application/json" --data-binary "@examples/search-request.json"`. The MCP Inspector also needs Node.js and `npx` on `PATH`.

## Tests

The test suite uses only the bundled synthetic schema and starter corpus; it needs no ISO files, AWS credentials, or network access.

```bash
uv sync --extra dev --extra ai
uv run pytest
uv run ruff check app tests
```

The MCP server test is skipped when the optional `ai` extra is not installed. `tests/test_evaluations.py` runs every case in `data/evaluations/starter.jsonl` as a regression test. CI runs the same checks on Python 3.11 and 3.12 and builds the frontend.

## Detailed roadmap: MCP + grounded LLM

### Step 1 — Load a small, traceable corpus

- Use one official `pacs.008` XSD version and one or two permitted reference documents.
- Keep the complete message ID/version with all schema, document, and retrieval metadata.
- Expand `data/knowledge/sources.json` with a stable ID, document title, version/message ID (when specific), official URL, local filename, and retrieval date.
- Preserve headings and page/section references during extraction so citations can identify where a passage came from.
- Keep restricted source files out of Git unless redistribution is allowed. Commit the manifest, original project notes, ingestion code, and instructions instead.
- Add more message versions only after version-filtered retrieval and validation work correctly.

### Step 2 — Extract reusable deterministic services

- XSD validation, registry loading, and document lookup live in `app/services/` and are shared by HTTP and MCP adapters.
- Add richer ingestion/search (section and page retention, chunking, and eventually embedding-based retrieval) without changing the service contract.
- Return stable machine-readable errors for malformed XML, unknown message versions, unavailable schemas, and XSD failures.
- Keep schema selection allowlisted; disable external entity/network resolution and apply request/result limits.

### Step 3 — Expose the services through MCP

The server uses the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), is an optional `ai` dependency extra, and defaults to local stdio transport. The server and Bedrock client are implemented, and the test suite exercises every tool through the in-memory MCP client; Inspector verification remains to be added.

Initial tools:

| Tool | Inputs | Result |
| --- | --- | --- |
| `list_supported_messages` | none | Registered message IDs/versions and local schema availability |
| `validate_message` | `message_id`, `xml` | Deterministic validity and structured diagnostics |
| `check_cbpr_postal_addresses` | `xml`, optional `enforce_unstructured_removal` | Per-address format and CBPR+ findings with XPath and suggested fix |
| `check_sepa_sct` | `xml`, optional `enforce_unstructured_address_removal` | Per-transaction EPC SCT findings with XPath and suggested fix |
| `validate_iban` / `validate_bic` | `iban` / `bic` | Format, structure, check digits, parts and SEPA membership |
| `search_iso_documents` | `query`, optional `message_id`, `limit` | Excerpts with source ID, version, section/page, and provenance |
| `explain_validation_error` | `message_id`, error details | Matching source excerpts; no invented rule when no source matches |

The tools return structured results. The MCP server provides tools; it does not call the model itself. The Bedrock client supplies the model's tool calls to the MCP client and passes results back through Converse.

### Step 4 — Connect the optional LLM client

- The React assistant calls FastAPI `/api/v1/ask`; `app/llm/bedrock.py` uses the official in-memory MCP client and AWS Bedrock Converse tool use.
- Keep provider-specific orchestration isolated; add another adapter only when needed.
- Let the client discover tools, send the user's question and tool definitions to the model, validate model tool arguments, execute requested MCP calls, and return tool results for a final explanation.
- Require the answer to cite only source IDs actually returned by search. If retrieval has no relevant evidence, say so.
- Display deterministic validation status/errors separately from generated explanation.
- Keep this feature optional: core validation/search must work without model credentials.
- Store credentials only in the normal AWS credential chain or ignored environment configuration. Never commit keys, prompts containing sensitive data, or customer XML.

### Step 5 — Expand samples and evaluate behavior

- Add synthetic valid and invalid XML fixtures for the exact selected XSD version: malformed XML, missing required content, invalid code/value, and unsupported version.
- Derive each expected validation outcome by running the deterministic validator against the local schema; do not guess expected results.
- A starter JSONL set is in `data/evaluations/starter.jsonl`; expand it with cases for the selected schema, expected source IDs, and criteria for a correct answer. Keep copyrighted excerpts out unless their terms permit it.
- Track validation expected-result accuracy, retrieval hit@k/recall@k, version-filter correctness, citation correctness, and manually reviewed grounded-answer quality.
- Measure latency and model/token cost for the LLM path only if it is implemented.
- Publish measured results with the dataset size and limitations. Do not state targets or performance numbers before running the evaluation.

## Example expected behavior

### Deterministic validation

Input: synthetic XML and an explicitly registered message version.

Expected: a JSON result containing that message ID, `valid: true|false`, a result kind, and structured diagnostics. A parser error, unsupported version, unavailable XSD, and schema error are distinct conditions. The exact XSD diagnostics depend on the downloaded version and parser.

### Grounded assistant

Question: “Why did this synthetic `pacs.008` message fail validation?”

Expected flow: call `validate_message` → search for the relevant field/rule → explain the validator's result → cite returned source IDs → clearly state that XSD validity does not prove scheme or bank compliance. If no source supports the explanation, say it cannot be confirmed from the loaded corpus.

## Data handling and limits

- Use synthetic sample messages only. Do not use production payment traffic or internal employer documentation.
- Keep downloaded XSDs/documents local unless redistribution terms explicitly permit committing them.
- Do not commit `.env`, API keys, AWS credentials, or private source documents.
- Treat retrieved document text and XML as untrusted data, never as instructions for the model.
- XSD validity is not scheme-level or institution-level compliance.
- The current search is basic token overlap over local Markdown; it is not semantic RAG and should not be described as such.

## Publish to GitHub

This project is published at [github.com/Yuussef/Iso20022-Mcp](https://github.com/Yuussef/Iso20022-Mcp). Clone it with:

```bash
git clone https://github.com/Yuussef/Iso20022-Mcp.git
cd Iso20022-Mcp
```

To publish later changes, commit them on `main` and run `git push`. Do not force-add local XSDs or `.env` files; `.gitignore` excludes them by default. `frontend/package-lock.json` is committed, so use `npm ci` for reproducible installs.

## References

- [ISO 20022 Message Definitions catalogue](https://www.iso20022.org/iso-20022-message-definitions)
- [ISO 20022 Catalogue of Messages](https://www.iso20022.org/catalogue-messages)
- [ISO 20022 FAQ](https://www.iso20022.org/faq)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## License and source-data note

The original project code is released under the [MIT License](LICENSE). This license does not automatically grant redistribution rights to ISO schemas, message reports, or other third-party materials. Keep source files, provenance, and their terms clearly documented and separate from original code.
