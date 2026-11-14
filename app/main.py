from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.cbpr_pacs008 import check_cbpr_pacs008
from app.services.identifiers import validate_bic, validate_iban
from app.services.knowledge_search import search_documents
from app.services.mt103 import MAX_MT_CHARS, Mt103Error, convert_mt103
from app.services.payment_summary import summarize_payment
from app.services.postal_address import check_postal_addresses
from app.services.registry import SchemaUnavailableError, supported_messages
from app.services.sepa_sct import check_sepa_sct
from app.services.validation import (
    MAX_XML_CHARS,
    SchemaConfigurationError,
    ValidatorUnavailableError,
)
from app.services.validation import (
    validate_message as validate_xml_message,
)

app = FastAPI(
    title="PayDoc AI API",
    description=(
        "Deterministic ISO 20022 schema validation, SEPA Credit Transfer and CBPR+ usage-rule checks, "
        "IBAN/BIC validation and source-backed lookup."
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ValidationRequest(BaseModel):
    message_id: str = Field(pattern=r"^[a-z0-9]{4}\.\d{3}\.\d{3}\.\d{2,3}$")
    xml: str = Field(min_length=1, max_length=MAX_XML_CHARS)


class PostalAddressCheckRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=MAX_XML_CHARS)
    enforce_unstructured_removal: bool = Field(
        default=False,
        description="Treat unstructured addresses as errors. Off by default because Swift deferred their removal.",
    )


class SepaCheckRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=MAX_XML_CHARS)
    enforce_unstructured_address_removal: bool = Field(
        default=False,
        description="Treat unstructured addresses as errors. Off by default because the EPC deferred their end date.",
    )


class XmlRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=MAX_XML_CHARS)


class Mt103Request(BaseModel):
    mt: str = Field(min_length=1, max_length=MAX_MT_CHARS, description="MT103 text, with or without the {1:}{2:}{3:}{4:} blocks.")


class IdentifierRequest(BaseModel):
    value: str = Field(min_length=1, max_length=100)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    message_id: str | None = Field(default=None, pattern=r"^[a-z0-9]{4}\.\d{3}\.\d{3}\.\d{2,3}$")
    limit: int = Field(default=5, ge=1, le=10)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "paydoc-ai"}


@app.get("/api/v1/messages")
def list_messages() -> dict[str, Any]:
    return supported_messages()


@app.post("/api/v1/validate")
def validate(payload: ValidationRequest) -> dict[str, Any]:
    try:
        return validate_xml_message(payload.message_id, payload.xml)
    except SchemaUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No local XSD is configured for {exc}. Add an approved schema file "
                "and register it in data/schemas/registry.json."
            ),
        ) from exc
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to validate XSD.") from exc
    except SchemaConfigurationError as exc:
        raise HTTPException(status_code=500, detail="The configured local XSD could not be loaded.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


@app.post("/api/v1/checks/postal-address")
def check_postal_address(payload: PostalAddressCheckRequest) -> dict[str, Any]:
    try:
        return check_postal_addresses(payload.xml, payload.enforce_unstructured_removal)
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to check XML.") from exc


@app.post("/api/v1/checks/sepa-sct")
def check_sepa_credit_transfer(payload: SepaCheckRequest) -> dict[str, Any]:
    try:
        return check_sepa_sct(payload.xml, payload.enforce_unstructured_address_removal)
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to check XML.") from exc


@app.post("/api/v1/checks/cbpr-pacs008")
def check_cbpr_customer_credit_transfer(payload: PostalAddressCheckRequest) -> dict[str, Any]:
    try:
        return check_cbpr_pacs008(payload.xml, payload.enforce_unstructured_removal)
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to check XML.") from exc


@app.post("/api/v1/summaries/payment")
def summarize_credit_transfer(payload: XmlRequest) -> dict[str, Any]:
    try:
        return summarize_payment(payload.xml)
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to read XML.") from exc


@app.post("/api/v1/convert/mt103")
def convert_mt103_message(payload: Mt103Request) -> dict[str, Any]:
    try:
        return convert_mt103(payload.mt)
    except Mt103Error as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidatorUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Install the lxml dependency to build XML.") from exc


@app.post("/api/v1/identifiers/iban")
def check_iban(payload: IdentifierRequest) -> dict[str, Any]:
    return validate_iban(payload.value)


@app.post("/api/v1/identifiers/bic")
def check_bic(payload: IdentifierRequest) -> dict[str, Any]:
    return validate_bic(payload.value)


@app.post("/api/v1/search")
def search(payload: SearchRequest) -> dict[str, Any]:
    return search_documents(payload.query, payload.message_id, payload.limit)


@app.post("/api/v1/ask")
async def ask(payload: AskRequest) -> dict[str, Any]:
    if not os.getenv("BEDROCK_MODEL_ID", "").strip():
        raise HTTPException(
            status_code=503,
            detail="Configure BEDROCK_MODEL_ID and AWS credentials to enable the AI assistant.",
        )
    try:
        from app.llm.bedrock import answer_with_mcp_tools

        return await answer_with_mcp_tools(payload.question)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Install the optional AI dependencies with `uv sync --extra ai`.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="The configured AI model could not complete the request.") from exc


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
