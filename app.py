"""StegoShield Web Platform (Tasks L20 - L24).

A 4-module Streamlit dashboard for:
- Tab 1: Keys & Key Management (Module A)
- Tab 2: Pre-Flight Cover Image Audit & Capacity Checker (Module B)
- Tab 3: Hide & Extract Engine (Module C & A)
- Tab 4: Defensive AI Steganalysis Detector (Module D)
"""

from __future__ import annotations

import io
from pathlib import Path
from PIL import Image
import numpy as np
import streamlit as st

from core.crypto import (
    encrypt_password,
    decrypt_password,
    encrypt_asymmetric,
    decrypt_asymmetric,
    derive_permutation_key_from_password,
    derive_permutation_key_from_public_key,
    AuthenticationError,
    InvalidPayloadError,
)
from core.keys import (
    generate_keypair,
    export_private_key_pem,
    import_private_key_pem,
    export_public_key_pem,
    export_public_key_base64,
    import_public_key_auto,
)
from core.capacity import calculate_image_capacity, compute_payload_ratio, CapacityExceededError
from core.embed import embed_payload, extract_payload
from ml.detector import StegoDetector
from ml.risk import PreFlightRiskScorer
from ml.features import extract_features, FEATURE_NAMES


# Page Configuration
st.set_page_config(
    page_title="StegoShield | Encrypted Steganography & AI Steganalysis",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished interface
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .stCard {
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid rgba(128, 128, 128, 0.2);
        margin-bottom: 1rem;
    }
    .badge-low {
        background-color: #d4edda;
        color: #155724;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
    }
    .badge-med {
        background-color: #fff3cd;
        color: #856404;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
    }
    .badge-high {
        background-color: #f8d7da;
        color: #721c24;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# Session State Initialization
# ==============================================================================

if "shared_password" not in st.session_state:
    st.session_state.shared_password = ""
if "active_private_key" not in st.session_state:
    st.session_state.active_private_key = None
if "active_public_key" not in st.session_state:
    st.session_state.active_public_key = None
if "recipient_public_key" not in st.session_state:
    st.session_state.recipient_public_key = None
if "audited_image" not in st.session_state:
    st.session_state.audited_image = None
if "stego_result_image" not in st.session_state:
    st.session_state.stego_result_image = None


# Cached Models
@st.cache_resource
def get_detector() -> StegoDetector:
    return StegoDetector()

@st.cache_resource
def get_risk_scorer() -> PreFlightRiskScorer:
    return PreFlightRiskScorer()


detector = get_detector()
risk_scorer = get_risk_scorer()


# Header
st.markdown('<div class="main-title">🛡️ StegoShield</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Smart Web Platform for Authenticated Encrypted Steganography and Defensive AI Steganalysis</div>',
    unsafe_allow_html=True,
)

# Tabs Navigation
tab_keys, tab_audit, tab_hide_extract, tab_detector = st.tabs([
    "🔑 Module A: Keys & Key Management",
    "🔍 Module B: Pre-Flight Cover Audit",
    "🔒 Module C: Hide & Extract Engine",
    "🛡️ Module D: Defensive AI Detector",
])


# ==============================================================================
# TAB 1: Keys & Key Management (Module A)
# ==============================================================================

with tab_keys:
    st.header("Cryptographic Key Management")
    st.caption("Manage pre-shared passwords for PBKDF2 symmetric mode or generate and import X25519 elliptic-curve keypairs for asymmetric mode.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. Pre-Shared Password Mode")
        st.write("Used for symmetric AES-256-GCM encryption with PBKDF2-HMAC-SHA256 (600,000 iterations).")
        pw_input = st.text_input(
            "Shared Secret Password",
            value=st.session_state.shared_password,
            type="password",
            placeholder="Enter shared secret password...",
            help="This password derives the encryption key and pseudorandom permutation seed.",
        )
        if pw_input:
            st.session_state.shared_password = pw_input
            st.success("✅ Shared password stored in active session.")

        st.divider()

        st.subheader("3. Recipient Public Key (for Sending Asymmetric Data)")
        st.write("Import your recipient's X25519 public key to encrypt payloads without sharing passwords.")
        pub_import_input = st.text_area(
            "Paste Recipient Public Key (PEM, Base64, or Hex)",
            height=110,
            placeholder="MCowBQYDK2VuAyEA... or standard PEM",
        )
        pub_file = st.file_uploader("Or upload .pub / .pem file", type=["pem", "pub", "txt"], key="recipient_pub_file")

        if pub_file is not None:
            pub_import_input = pub_file.read().decode("utf-8", errors="replace")

        if st.button("Import Recipient Key"):
            if pub_import_input.strip():
                try:
                    loaded_pub = import_public_key_auto(pub_import_input)
                    st.session_state.recipient_public_key = loaded_pub
                    st.success("✅ Recipient public key validated and stored in session!")
                except Exception as e:
                    st.error(f"❌ Failed to parse public key: {e}")
            else:
                st.warning("Please provide a public key string or upload a key file.")

        if st.session_state.recipient_public_key is not None:
            st.info("Active Recipient Key: `Valid X25519 Key ready for asymmetric embedding`")

    with col2:
        st.subheader("2. Asymmetric Key Generator (X25519 ECDH)")
        st.write("Generate a fresh public/private keypair for secure asymmetric steganography.")

        passphrase = st.text_input("Optional Private Key Passphrase", type="password", help="Encrypts exported private key with AES")

        if st.button("Generate New X25519 Keypair", type="primary"):
            priv, pub = generate_keypair()
            st.session_state.active_private_key = priv
            st.session_state.active_public_key = pub
            st.success("🎉 New keypair generated!")

        if st.session_state.active_private_key is not None and st.session_state.active_public_key is not None:
            priv_pem = export_private_key_pem(st.session_state.active_private_key, password=passphrase or None)
            pub_pem = export_public_key_pem(st.session_state.active_public_key)
            pub_b64 = export_public_key_base64(st.session_state.active_public_key)

            st.write("**Your Public Key (Share this with senders):**")
            st.code(pub_b64, language="text")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    "📥 Download Public Key (PEM)",
                    data=pub_pem,
                    file_name="stegoshield_public.pem",
                    mime="application/x-pem-file",
                )
            with col_d2:
                st.download_button(
                    "📥 Download Private Key (PEM)",
                    data=priv_pem,
                    file_name="stegoshield_private.pem",
                    mime="application/x-pem-file",
                )


# ==============================================================================
# TAB 2: Pre-Flight Cover Image Audit (Module B)
# ==============================================================================

with tab_audit:
    st.header("Pre-Flight Cover Image Audit & Capacity Checker")
    st.caption("Inspect carrier image statistics, evaluate maximum safe payload limits, and predict AI detectability risk before committing to steganography.")

    cover_file = st.file_uploader(
        "Upload Candidate Cover Image",
        type=["png", "jpg", "jpeg", "bmp"],
        key="audit_uploader",
    )

    if cover_file is not None:
        cover_img = Image.open(cover_file)
        st.session_state.audited_image = cover_img

        col_img, col_metrics = st.columns([1, 2])

        with col_img:
            st.image(cover_img, caption=f"Carrier: {cover_file.name} ({cover_img.width}x{cover_img.height})", use_container_width=True)

        with col_metrics:
            cap = calculate_image_capacity(cover_img)
            st.subheader("Carrier Capacity Limits")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Image Size", f"{cover_img.width} x {cover_img.height}")
            m2.metric("Total Slots", f"{cap['total_carrier_bits']:,} bits")
            m3.metric("Safe Payload (10%)", f"{cap['safe_payload_bytes']:,} B")
            m4.metric("Max Capacity", f"{cap['max_payload_bytes']:,} B")

            st.divider()

            st.subheader("Simulate Planned Payload")
            sim_bytes = st.slider(
                "Planned Payload Size (Bytes)",
                min_value=0,
                max_value=cap["max_payload_bytes"],
                value=min(cap["safe_payload_bytes"], 500),
                step=10,
            )

            # Evaluate Risk
            audit_result = risk_scorer.evaluate(cover_img, target_payload_bytes=sim_bytes)

            st.subheader("Detectability Risk Assessment")
            r_col1, r_col2 = st.columns([1, 2])
            with r_col1:
                st.markdown(f"### {audit_result['risk_badge']}")
                st.markdown(f"**Score:** `{audit_result['risk_score_percent']}`")
                st.progress(audit_result["risk_score"])
            with r_col2:
                st.info(f"**Recommendation:** {audit_result['recommendation']}")

            st.write(f"**Texture Profile:** {audit_result['texture_description']}")

            # Detailed Feature Table
            with st.expander("🔬 View Image Statistical Features"):
                f_cols = st.columns(4)
                f_cols[0].metric("Laplacian Variance", audit_result["features"]["laplacian_variance"])
                f_cols[1].metric("Sobel Edge Energy", audit_result["features"]["edge_energy"])
                f_cols[2].metric("Histogram Entropy", audit_result["features"]["histogram_entropy"])
                f_cols[3].metric("LSB Mean", audit_result["features"]["lsb_mean"])


# ==============================================================================
# TAB 3: Hide & Extract Engine (Module C & A)
# ==============================================================================

with tab_hide_extract:
    st.header("Steganographic Hide & Extract Engine")
    st.caption("Encrypt payloads with AES-256-GCM and embed them across pixel channels using key-seeded pseudorandom permutations.")

    op_mode = st.radio("Choose Operation", ["🔒 Hide Secret Message", "🔓 Extract Hidden Message"], horizontal=True)

    if op_mode == "🔒 Hide Secret Message":
        st.subheader("Embed Message into Cover Image")

        c1, c2 = st.columns([1, 1])
        with c1:
            embed_cover_file = st.file_uploader(
                "Upload Cover Image (PNG recommended)",
                type=["png", "jpg", "jpeg", "bmp"],
                key="embed_cover_uploader",
            )
            if embed_cover_file is None and st.session_state.audited_image is not None:
                if st.checkbox("Use audited image from Tab 2"):
                    active_cover = st.session_state.audited_image
                else:
                    active_cover = None
            elif embed_cover_file is not None:
                active_cover = Image.open(embed_cover_file)
            else:
                active_cover = None

            if active_cover:
                st.image(active_cover, caption="Active Cover Carrier", width=280)

        with c2:
            enc_mode = st.selectbox(
                "Encryption Mode",
                ["Password (PBKDF2-HMAC-SHA256 + AES-256-GCM)", "Asymmetric (X25519 ECDH + AES-256-GCM)"],
            )

            algo_choice = st.selectbox(
                "Embedding Algorithm",
                ["replacement", "matching"],
                format_func=lambda x: "Standard LSB Replacement" if x == "replacement" else "LSB Matching (+/-1 Embedding, Anti-PoV)",
            )

            perm_choice = st.selectbox(
                "Permutation Mapping",
                ["pseudorandom", "sequential"],
                format_func=lambda x: "Key-Seeded Pseudorandom (Scattered, Defeats Sequential Extraction)" if x == "pseudorandom" else "Sequential (Baseline comparison)",
            )

            secret_msg = st.text_area("Secret Plaintext Message", height=120, placeholder="Enter confidential message to conceal...")

        if st.button("🚀 Encrypt & Conceal in Image", type="primary"):
            if not active_cover:
                st.error("Please upload or select a cover image.")
            elif not secret_msg.strip():
                st.error("Please provide a secret message.")
            else:
                try:
                    with st.spinner("Encrypting payload and scattering bits across image channels..."):
                        if "Password" in enc_mode:
                            pwd = st.session_state.shared_password
                            if not pwd:
                                st.error("Please set a password in Tab 1 (or enter one now).")
                                st.stop()
                            payload_bytes, perm_key = encrypt_password(secret_msg, pwd)
                        else:
                            recipient_pub = st.session_state.recipient_public_key
                            if not recipient_pub:
                                st.error("Please import a Recipient Public Key in Tab 1 first.")
                                st.stop()
                            payload_bytes, perm_key = encrypt_asymmetric(secret_msg, recipient_pub)

                        eff_key = perm_key if perm_choice == "pseudorandom" else None
                        stego_img = embed_payload(
                            cover_image=active_cover,
                            payload_bytes=payload_bytes,
                            perm_key=eff_key,
                            mode=perm_choice,
                            algorithm=algo_choice,
                        )
                        st.session_state.stego_result_image = stego_img

                    st.success("🎉 Stego-Image generated successfully! All bits scattered and encrypted.")

                    buf = io.BytesIO()
                    stego_img.save(buf, format="PNG")
                    stego_bytes = buf.getvalue()

                    st.download_button(
                        "📥 Download Stego Image (PNG)",
                        data=stego_bytes,
                        file_name="stegoshield_stego.png",
                        mime="image/png",
                        type="primary",
                    )
                except CapacityExceededError as ce:
                    st.error(f"❌ Capacity Error: {ce}")
                except Exception as e:
                    st.error(f"❌ Error during embedding: {e}")

    else:
        st.subheader("Extract & Authenticate Hidden Message")

        ext_c1, ext_c2 = st.columns([1, 1])
        with ext_c1:
            stego_upload = st.file_uploader(
                "Upload Stego Image (PNG format)",
                type=["png"],
                key="extract_uploader",
            )
            if stego_upload:
                stego_in_img = Image.open(stego_upload)
                st.image(stego_in_img, caption="Stego Carrier", width=280)
            else:
                stego_in_img = None

        with ext_c2:
            ext_enc_mode = st.selectbox(
                "Decryption Mode",
                ["Password Mode", "Asymmetric Mode (Private Key)"],
                key="ext_enc_mode",
            )
            ext_perm_choice = st.selectbox(
                "Extraction Permutation",
                ["pseudorandom", "sequential"],
                format_func=lambda x: "Key-Seeded Pseudorandom (Default)" if x == "pseudorandom" else "Sequential (Baseline)",
                key="ext_perm_choice",
            )

            if ext_enc_mode == "Password Mode":
                ext_password = st.text_input(
                    "Enter Password",
                    value=st.session_state.shared_password,
                    type="password",
                    key="ext_password",
                )
            else:
                priv_file = st.file_uploader("Upload Private Key PEM", type=["pem", "key", "txt"], key="priv_uploader")
                priv_pass = st.text_input("Private Key Passphrase (if encrypted)", type="password", key="priv_pass")

        if st.button("🔓 Extract & Decrypt Secret", type="primary"):
            if not stego_in_img:
                st.error("Please upload a stego image.")
            else:
                try:
                    with st.spinner("Extracting scattered bits and verifying AES-256-GCM authentication tag..."):
                        if ext_enc_mode == "Password Mode":
                            if not ext_password:
                                st.error("Please enter the decryption password.")
                                st.stop()
                            eff_perm = derive_permutation_key_from_password(ext_password) if ext_perm_choice == "pseudorandom" else None
                            payload_bytes = extract_payload(stego_in_img, perm_key=eff_perm, mode=ext_perm_choice)
                            plaintext = decrypt_password(payload_bytes, ext_password)
                        else:
                            if not priv_file:
                                st.error("Please upload your private key PEM.")
                                st.stop()
                            pem_str = priv_file.read().decode("utf-8", errors="replace")
                            priv_key = import_private_key_pem(pem_str, password=priv_pass or None)
                            pub = priv_key.public_key()
                            eff_perm = derive_permutation_key_from_public_key(pub) if ext_perm_choice == "pseudorandom" else None
                            payload_bytes = extract_payload(stego_in_img, perm_key=eff_perm, mode=ext_perm_choice)
                            plaintext = decrypt_asymmetric(payload_bytes, priv_key)

                    st.success("✅ Payload authenticated and decrypted successfully!")
                    st.text_area("Decrypted Secret Message", value=plaintext.decode("utf-8", errors="replace"), height=140)

                except AuthenticationError:
                    st.error("🛡️ Security Verification Failed: Authentication tag mismatch. Wrong key or the image was tampered with.")
                except InvalidPayloadError as ip:
                    st.error(f"🛡️ Safe Extraction Failure: {ip}")
                except Exception as e:
                    st.error(f"❌ Extraction error: {e}")


# ==============================================================================
# TAB 4: Defensive AI Steganalysis Detector (Module D)
# ==============================================================================

with tab_detector:
    st.header("Defensive AI Steganalysis Detector")
    st.caption("Inspect unknown images for steganographic anomalies using 27 statistical features (Chi-square test, LSB autocorrelation, and spatial co-occurrence).")

    detect_file = st.file_uploader(
        "Upload Image for AI Steganalysis",
        type=["png", "jpg", "jpeg", "bmp"],
        key="detect_uploader",
    )

    if detect_file is not None:
        suspect_img = Image.open(detect_file)

        col_d_img, col_d_results = st.columns([1, 2])

        with col_d_img:
            st.image(suspect_img, caption=f"Analyzed: {detect_file.name}", use_container_width=True)

        with col_d_results:
            if st.button("🔍 Run Steganalysis Scan", type="primary"):
                with st.spinner("Extracting 27 feature statistics and running detector..."):
                    result = detector.predict(suspect_img)

                st.subheader(f"Detection Verdict: {result['badge']}")
                prob = result["probability"]

                p_col1, p_col2 = st.columns([1, 2])
                with p_col1:
                    st.metric("Stego Probability", result["probability_percent"])
                    st.progress(prob)
                with p_col2:
                    st.write(f"**Confidence Level:** {result['confidence']}")
                    st.write(f"**Detector Engine:** `{result['model_type']}`")

                st.divider()
                st.subheader("Statistical Anomaly Indicators")
                if result["anomalies"]:
                    for a in result["anomalies"]:
                        st.warning(f"⚠️ **{a['metric']}**: {a['finding']}")
                else:
                    st.success("✅ No statistical anomalies found. Pairs-of-values and bit-plane transitions reflect clean carrier characteristics.")

                with st.expander("📊 Complete 27-Feature Inspection"):
                    st.json(result["features"])

