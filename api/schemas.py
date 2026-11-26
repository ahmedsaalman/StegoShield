"""Request and response models. These define the public API contract (see /api/docs)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class KeyMethod(StrEnum):
    PASSWORD = "password"
    PUBLIC_KEY = "public_key"


class EmbeddingAlgorithmChoice(StrEnum):
    REPLACEMENT = "replacement"
    MATCHING = "matching"


class EmbeddingLayoutChoice(StrEnum):
    PSEUDORANDOM = "pseudorandom"
    SEQUENTIAL = "sequential"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Verdict(StrEnum):
    CLEAN = "clean"
    LIKELY_CLEAN = "likely_clean"
    SUSPICIOUS = "suspicious"
    STEGO = "stego"


class MessageEncoding(StrEnum):
    UTF8 = "utf-8"
    BASE64 = "base64"


class HealthResponse(BaseModel):
    status: str = "ok"


class DetectorStatus(BaseModel):
    available: bool = Field(description="False until a trained detector matching this code is installed.")
    model_type: str
    trained_at: str | None = None
    unavailable_reason: str | None = None


class Limits(BaseModel):
    max_upload_bytes: int
    max_image_pixels: int
    max_message_bytes: int
    rate_limit_per_minute: int


class MetaResponse(BaseModel):
    version: str
    limits: Limits
    detector: DetectorStatus


class KeyGenerationRequest(BaseModel):
    passphrase: str | None = Field(default=None, max_length=1024, description="Encrypts the exported private key.")


class KeyPairResponse(BaseModel):
    public_key_base64: str
    public_key_pem: str
    private_key_pem: str
    fingerprint: str
    is_private_key_encrypted: bool


class PublicKeyInspectRequest(BaseModel):
    public_key: str = Field(min_length=1, max_length=4096, description="PEM, Base64 or hex X25519 public key.")


class PublicKeyInfo(BaseModel):
    public_key_base64: str
    fingerprint: str


class MessageCapacity(BaseModel):
    password: int = Field(description="Largest message in bytes when protected with a password.")
    public_key: int = Field(description="Largest message in bytes when encrypted to a public key.")


class CapacityResponse(BaseModel):
    width: int
    height: int
    channels: int
    is_lossy_source: bool
    max_message_bytes: MessageCapacity


class RiskAssessment(BaseModel):
    probability: float = Field(ge=0.0, le=1.0)
    level: RiskLevel
    method: str = Field(description="How the risk was estimated, in words.")


class PreflightResponse(BaseModel):
    capacity: CapacityResponse
    message_bytes: int
    method: KeyMethod
    fits: bool
    payload_percent: float = Field(description="Share of the image's embeddable bits the message would use.")
    recommended_max_message_bytes: int
    risk: RiskAssessment
    recommendation: str
    texture: str


class FeatureContribution(BaseModel):
    feature: str
    value: float
    typical_clean_value: float
    z_score: float = Field(description="Standard deviations from the average clean training cover.")
    contribution: float = Field(description="Feature importance × |z-score|; larger pushed the score more.")


class DetectionResponse(BaseModel):
    probability: float = Field(ge=0.0, le=1.0)
    verdict: Verdict
    is_stego: bool
    threshold: float
    model_type: str
    top_features: list[FeatureContribution]


class RevealResponse(BaseModel):
    message: str
    encoding: MessageEncoding
    message_bytes: int
