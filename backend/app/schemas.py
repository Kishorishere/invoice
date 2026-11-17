"""Pydantic schemas: request/response bodies and the invoice domain model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, PlainSerializer


# ---------- Money type -------------------------------------------------------
#
# Money fields are `Decimal` end-to-end so VAT arithmetic doesn't drift
# through float rounding. The BeforeValidator accepts int / float / str /
# Decimal so we stay backwards-compatible with existing rows (which stored
# amounts as JSON numbers) and so providers can still return naked numbers.
# Default pydantic-v2 JSON serialization renders Decimal as a string — exact,
# and what downstream accounting systems (UBL, Factur-X) expect.


def _to_decimal(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, bool):  # bool is an int subclass — reject explicitly
        raise TypeError("bool is not a valid money value")
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        try:
            return Decimal(v.strip())
        except (InvalidOperation, ValueError) as err:
            raise ValueError(f"Not a valid decimal: {v!r}") from err
    return v


def _decimal_to_json(v: Decimal) -> float:
    # Rendered in JSON responses + stored in data_json. Values are 2-decimal
    # currency amounts; float is the natural wire format for the frontend and
    # for downstream JSON consumers. In-memory arithmetic stays exact (Decimal).
    return float(v)


def _optional_decimal_to_json(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


Money = Annotated[
    Decimal,
    BeforeValidator(_to_decimal),
    PlainSerializer(_decimal_to_json, return_type=float, when_used="json"),
]
OptionalMoney = Annotated[
    Decimal | None,
    BeforeValidator(_to_decimal),
    PlainSerializer(
        _optional_decimal_to_json, return_type=float | None, when_used="json"
    ),
]


# ---------- Auth ----------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    role: Literal["user", "admin"] = "user"
    created_at: datetime


class AuthResponse(BaseModel):
    """Returned by /login. Session + CSRF live in cookies; the response body
    carries only the user profile. The client reads the CSRF value from the
    (non-HttpOnly) cookie to echo in headers."""

    user: UserPublic


# ---------- Admin: user management ----------


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "admin"] = "user"


class AdminUpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    role: Literal["user", "admin"] | None = None


class AdminResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminUserRow(BaseModel):
    id: str
    email: EmailStr
    role: Literal["user", "admin"]
    created_at: datetime
    invoice_count: int


# ---------- Invoice domain ----------


class Party(BaseModel):
    """Supplier or bill-to party."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class InvoiceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str
    # Quantity kept as string to preserve "50 pcs" / "10 hrs" / "1 lot".
    quantity: str
    unit_price: Money
    total: Money


class InvoiceData(BaseModel):
    """The structured invoice payload returned by the AI provider."""

    # validate_assignment: so direct attribute writes (e.g. `inv.subtotal = x`
    # in tests or post-extraction edits) run the Money BeforeValidator and
    # keep the Decimal invariant across the whole object.
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    invoice_number: str
    invoice_date: str | None = None  # ISO 8601 (YYYY-MM-DD) when parseable
    due_date: str | None = None
    payment_terms: str | None = None

    supplier: Party = Field(default_factory=Party)
    bill_to: Party = Field(default_factory=Party)

    items: list[InvoiceItem] = Field(default_factory=list)

    subtotal: OptionalMoney = None
    vat_rate: OptionalMoney = None  # percentage, e.g. 13.0
    vat_amount: OptionalMoney = None
    total: Money

    currency: str = "NPR"
    notes: list[str] = Field(default_factory=list)


# ---------- Validation ----------

CheckStatus = Literal["pass", "fail", "skipped"]


class ValidationCheck(BaseModel):
    name: str
    status: CheckStatus
    message: str
    delta: OptionalMoney = None  # signed difference where applicable


class ValidationResult(BaseModel):
    checks: list[ValidationCheck]
    all_pass: bool
    due_status: Literal["paid", "due_soon", "due_later", "overdue", "unknown"] = "unknown"
    days_until_due: int | None = None


# ---------- Extract response ----------


class ExtractResponse(BaseModel):
    invoice_id: str
    provider: str
    model: str | None = None
    data: InvoiceData
    validation: ValidationResult
    created_at: datetime


class DuplicateDetail(BaseModel):
    """Structured 409 body when /extract hits an existing row for this user.

    Carries enough context for the client to render a "looks familiar" card
    inline — supplier + amount + age — without a second round-trip to
    /invoices/{id}. The client can also link to /invoice/:id to view in full.
    """

    message: str
    duplicate_of: str  # invoice_id of the existing row
    uploaded_at: datetime
    invoice_number: str | None = None
    supplier_name: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    all_checks_pass: bool = False


class InvoiceListItem(BaseModel):
    id: str
    provider: str
    model: str | None = None
    invoice_number: str | None
    supplier_name: str | None
    # Denormalized for list sorting/filtering; authoritative value lives in
    # data_json as a Decimal-faithful string. float is fine here.
    total_amount: float | None
    currency: str | None
    invoice_date: str | None
    due_date: str | None
    all_checks_pass: bool
    created_at: datetime
    mime_type: str


class ProvidersInfo(BaseModel):
    available: list[str]
    default: str | None


class ModelInfo(BaseModel):
    id: str
    label: str


class ModelsResponse(BaseModel):
    provider: str
    default: str | None
    models: list[ModelInfo]
    cached: bool


# ---------- Limits / quotas ----------


class LimitsConfig(BaseModel):
    max_files_per_upload: int = Field(ge=1, le=100)
    max_per_hour: int = Field(ge=1)
    max_per_day: int = Field(ge=1)
    max_per_month: int = Field(ge=1)


class LimitsPatch(BaseModel):
    max_files_per_upload: int | None = Field(default=None, ge=1, le=100)
    max_per_hour: int | None = Field(default=None, ge=1)
    max_per_day: int | None = Field(default=None, ge=1)
    max_per_month: int | None = Field(default=None, ge=1)


class WindowCounts(BaseModel):
    hour: int
    day: int
    month: int


class WindowResets(BaseModel):
    hour: datetime
    day: datetime
    month: datetime


class LimitsStatus(BaseModel):
    limits: LimitsConfig
    usage: WindowCounts
    remaining: WindowCounts
    reset_at: WindowResets
