from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class Requirement(BaseModel):
    id: str = ""
    text: str = Field(max_length=300)
    type: Literal["requirement", "knockout"] = "requirement"


class Knockout(BaseModel):
    kind: Literal["min_years", "skill", "language", "education"]
    value: str | float | int
    level: str | None = None


class LanguageReq(BaseModel):
    code: str = Field(max_length=5)
    level: Literal["A1", "A2", "B1", "B2", "C1", "C2"] = "B2"


class JobDraft(BaseModel):
    """The single job template every entry channel converges on."""
    title: str = Field("", max_length=200)
    description: str = Field("", max_length=8000)
    missions: list[str] = []
    city: str = Field("", max_length=120)
    country: str = Field("", max_length=80)
    remote: Literal["onsite", "hybrid", "remote"] = "onsite"
    contract_type: Literal["", "permanent", "fixed_term", "internship", "apprenticeship", "freelance"] = ""
    min_years_experience: float = Field(0, ge=0, le=40)
    education_level: int = Field(0, ge=0, le=8)
    languages: list[LanguageReq] = []
    skills_required: list[str] = Field([], max_length=30)
    skills_nice: list[str] = Field([], max_length=30)
    requirements: list[Requirement] = Field([], max_length=15)
    knockouts: list[Knockout] = Field([], max_length=8)
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = Field("", max_length=6)
    lang: Literal["fr", "en", "ar"] = "fr"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    role: Literal["candidate", "recruiter"]
    organization_name: str | None = Field(None, max_length=200)
    locale: Literal["fr", "en", "ar"] = "fr"
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def must_accept(cls, v):
        if not v:
            raise ValueError("terms must be accepted")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None


class PolicyIn(BaseModel):
    mode: Literal["TOP_N", "THRESHOLD", "TOP_N_FLOOR"]
    n: int = Field(10, ge=1, le=200)
    threshold: float = Field(65, ge=0, le=100)
    cap: int | None = Field(None, ge=1, le=200)


class MoveIn(BaseModel):
    to: Literal["to_contact", "interview", "offer", "hired", "rejected"]
    reason: str = ""
    message: str = Field("", max_length=2000)


class BulkRejectIn(BaseModel):
    application_ids: list[str] = Field(min_length=1, max_length=200)
    reason: Literal["skills", "experience", "position_filled", "other"]
    message: str = Field("", max_length=2000)
    reviewed: bool  # the recruiter confirms having seen the list with scores and reasons


class ChatIn(BaseModel):
    draft: JobDraft
    message: str = Field(min_length=1, max_length=6000)
    asked_field: str | None = None
    locked: list[str] = []


class FeedbackIn(BaseModel):
    type: Literal["should_be_in", "should_be_out", "requirement_wrong"]
    comment: str = Field(min_length=3, max_length=2000)


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sector: str = Field("", max_length=120)
    size: str = Field("", max_length=40)
    city: str = Field("", max_length=120)
    country: str = Field("", max_length=80)
    website: str = Field("", max_length=300)
    description: str = Field("", max_length=4000)
