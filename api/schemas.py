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


class ExampleKeyPairResponse(BaseModel):
    public_key_base64: str
    public_key_pem: str
    private_key_pem: str = Field(description="Public on purpose: anyone can read messages sent to the example key.")
    fingerprint: str


class PublicKeyInfo(BaseModel):
    public_key_base64: str
    fingerprint: str
    is_example_key: bool = Field(
        default=False, description="The key is the built-in example key, so anyone can read messages sent to it."
    )


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


# --- Evaluation Lab ---------------------------------------------------------------------------------


class LabOutcome(StrEnum):
    RECOVERED = "recovered"
    FAILED_SAFELY = "failed_safely"
    UNSAFE = "unsafe"


class QualityPoint(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    payload_percent: float = Field(description="Share of the image's embeddable bits filled with test data.")
    psnr_db: float | None = Field(description="Peak signal-to-noise ratio in dB; null if nothing changed.")
    ssim: float = Field(ge=-1.0, le=1.0, description="Structural similarity to the original (1 = identical).")


class LabQualityResponse(BaseModel):
    points: list[QualityPoint]


class TransportTrial(BaseModel):
    transport: str
    label: str
    outcome: LabOutcome


class LabRobustnessResponse(BaseModel):
    message_bytes: int
    trials: list[TransportTrial]


class AttackTrial(BaseModel):
    attack: str
    description: str
    outcome: LabOutcome


class LabAttacksResponse(BaseModel):
    trials: list[AttackTrial]


class DetectorPoint(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    payload_percent: float
    probability: float = Field(ge=0.0, le=1.0)
    is_detected: bool


class LabDetectorComparisonResponse(BaseModel):
    clean_probability: float = Field(ge=0.0, le=1.0, description="Detector score for the image as uploaded.")
    threshold: float
    points: list[DetectorPoint]


class SliceAuc(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    layout: EmbeddingLayoutChoice
    payload_percent: float
    roc_auc: float


class PreflightValidityRow(BaseModel):
    texture: str = Field(description="all, smooth or textured covers.")
    predicted_level: RiskLevel
    n_trials: int
    actual_detection_rate: float


class RobustnessRow(BaseModel):
    transport: str
    label: str
    n_trials: int
    recovered_rate: float
    failed_safely_rate: float
    unsafe_rate: float


class QualityRow(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    payload_percent: float
    psnr_mean_db: float
    ssim_mean: float


class LabResultsResponse(BaseModel):
    seed: int
    held_out_covers: int
    detector: list[SliceAuc]
    preflight_validity: list[PreflightValidityRow]
    robustness: list[RobustnessRow]
    quality: list[QualityRow]


# --- Evaluation Lab: live sample run ------------------------------------------------------------------


class SampleTexture(StrEnum):
    SMOOTH = "smooth"
    MEDIUM = "medium"
    TEXTURED = "textured"


class LabSample(BaseModel):
    id: str
    title: str
    texture: SampleTexture
    texture_complexity: float = Field(description="Laplacian variance; higher means more texture.")
    image_url: str


class LabSamplesResponse(BaseModel):
    samples: list[LabSample]
    source: str = Field(description="Where the sample photos come from and their licence.")


class LabSampleRunRequest(BaseModel):
    payload_percent: float = Field(ge=1, le=50, description="Share of each sample's embeddable bits to fill.")


class SampleAlgorithmResult(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    predicted_probability: float = Field(ge=0.0, le=1.0, description="Pre-flight prediction for this size.")
    predicted_level: RiskLevel
    actual_probability: float = Field(ge=0.0, le=1.0, description="Detector score on the real stego image.")
    is_detected: bool
    psnr_db: float | None = Field(description="Peak signal-to-noise ratio in dB; null if nothing changed.")
    ssim: float = Field(ge=-1.0, le=1.0)
    changed_values: int = Field(description="Colour values (R, G or B) that differ from the cover.")
    changed_share: float = Field(ge=0.0, le=1.0)
    stego_preview: str = Field(description="data: URL of a small JPEG preview of the stego image (display only).")
    change_map: str = Field(
        description="data: URL of a PNG map of changed values (centre 128×128 px, full resolution)."
    )


class LabSampleRunResponse(BaseModel):
    sample_id: str
    payload_percent: float
    message_bytes: int
    threshold: float
    results: list[SampleAlgorithmResult]


# --- Evaluation Lab: sample messages in the user's image ---------------------------------------------


class LabSampleText(BaseModel):
    id: str
    title: str
    description: str
    size_bytes: int
    text: str


class LabSampleTextsResponse(BaseModel):
    texts: list[LabSampleText]


class MessageCheck(BaseModel):
    check: str = Field(description="right_key, wrong_key, bit_flips, jpeg_q90 or resize_50.")
    label: str
    expected: LabOutcome
    outcome: LabOutcome


class PixelBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class SignalFeature(BaseModel):
    feature: str
    z_score: float


class MessageAlgorithmResult(BaseModel):
    algorithm: EmbeddingAlgorithmChoice
    predicted_probability: float = Field(ge=0.0, le=1.0)
    predicted_level: RiskLevel
    actual_probability: float = Field(ge=0.0, le=1.0)
    is_detected: bool
    psnr_db: float | None
    ssim: float = Field(ge=-1.0, le=1.0)
    changed_values: int
    changed_pixels: int
    flat_area_share: float = Field(ge=0.0, le=1.0, description="Share of the image in its flattest third of blocks.")
    flat_change_share: float = Field(
        ge=0.0, le=1.0, description="Share of changed pixels that fell in those flat blocks."
    )
    hotspot: PixelBox | None = Field(
        description="Flat area that received the most changes (original pixel coordinates)."
    )
    checks: list[MessageCheck]
    top_signals: list[SignalFeature]
    overview_image: str = Field(
        description="data: URL: dimmed image, changed pixels cyan, flat blocks red, hotspot box."
    )
    hotspot_original: str | None = Field(description="data: URL: the hotspot area of the original, full resolution.")
    hotspot_stego: str | None = Field(description="data: URL: the same area with changed pixels highlighted.")


class LabMessageRunResponse(BaseModel):
    text_id: str
    title: str
    message_bytes: int
    capacity_bytes: int
    fits: bool
    payload_percent: float
    threshold: float
    image_width: int
    image_height: int
    results: list[MessageAlgorithmResult]
