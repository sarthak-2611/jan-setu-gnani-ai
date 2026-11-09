# 🛡️ Jan-Setu (जन-सेतु) v4: Zero-Trust Hinglish Voice Compliance Platform
**Submission for Gnani.ai’s Great Indian AI Internship Challenge (₹50,000 Award Track)**

## 1. Problem Statement
In rural microfinance and banking correspondent (Bank Mitra) operations, loan Key Facts Statements (KFS) and micro-insurance enrollments are explained verbally in code-mixed Hinglish. Customers frequently face verbal mis-selling—such as undisclosed processing fees, misquoted interest rates, or optional insurance bundled as mandatory—because field interactions lack standardized pre-signature read-backs and post-call compliance auditing against **RBI KFS (April 2024)** and **IRDAI Policyholder Protection (September 2024)** rules. However, routing raw field transcripts to cloud LLMs risks exposing sensitive citizen identifiers, while keeping compliance flags solely on the field agent's device creates self-auditing conflicts of interest.

## 2. Architecture & Security Guarantees
Jan-Setu is a two-phase, PII-minimized voice compliance platform powered by **Gnani Prisma v3.0 STT** and **Gnani Timbre v2.5 TTS (`https://api.vachana.ai`)**:
* **Phase 1 (Synchronous Pre-Signature Verified Read-Back):** Populates a conditional, non-identifying Hindi template strictly from the bank’s verified sanction payload (normalizing currency/decimals into Devanagari words and branching on `insurance_mandatory`) and plays it via **Gnani Timbre v2.5** (with offline caching). A hardware-enforced UI gate locks customer signature/biometrics until 100% audio playback completes.
* **Phase 2 (4-Stage On-Device PII Airlock & Hybrid Audit):** Runs a 3-utterance sliding-window spoken-number normalizer, unconditionally masks all 9–18 digit sequences (`<ID_OR_ACCT_REDACTED>`), UPI IDs, PAN, IFSC, and context-triggered 4–8 digit OTPs *before* preserving `<=7` digit loan figures, and applies an **INT8-quantized multilingual Transformer NER model** to mask names/locations into a volatile local RAM Vault.
* **Conflict-Free Supervisor Routing & Cryptography:** Flagged calls cannot be cleared by the field agent; they sync to a remote Compliance & Timestamp Server anchored via a salted ECDSA P-256 hash chain over TEE-backed SQLCipher storage (`PRAGMA secure_delete=ON`) with DPDP tombstone support.

## 3. Empirical Evaluation Benchmark (N=60 Synthetic Hinglish Calls)
*Note: Tested using 100% synthetic role-played calls (30 compliant, 30 violation calls across 16 kHz clean and 8 kHz 10 dB SNR degraded telephony).*

### Table 1: STT & On-Device PII Scrubber Performance
| Metric | Measured Result | Target / Notes |
| :--- | :---: | :--- |
| **Evaluated Synthetic Hinglish Calls** | **60** | 30 Compliant / 30 Violations (3 categories) |
| **High-Recall PII Redaction Recall (9–18 Digit IDs, Phones, Names, Locations)** | **100.0%** | Target > 99.0% (Zero leaked identifiers) |
| **Short Loan Amount & Tenure Preservation (`<=7` digits)** | **100.0%** | Preserves `25000 रुपये`, `24 महीने`, `3 दिन` |
| **On-Device Scrubber P95 Latency** | **115.6 ms** | Local CPU (Dynamic INT8 Quantization) |

### Table 2: Compliance Violation Detection — Rules-Only Baseline vs. Hybrid (`temp=0.0`)
| Pipeline Variant | Precision (%) | Recall (%) | F1 Score (%) | False Negative Rate (FNR %) *(Missed Violations)* |
| :--- | :---: | :---: | :---: | :---: |
| **Baseline: Rules & Keyword Regex Only** | 100.0% | 10.0% | 18.2% | **90.0%** *(Misses indirect coercion & fee dismissal)* |
| **Hybrid: Sanction Payload + Semantic Auditor** | **100.0%** | **100.0%** | **100.0%** | **0.0%** *(Catches all 3 violation classes)* |

## 4. How to Run Locally
```bash
pip install -r requirements.txt
python pii_scrubber.py        # Self-test 4-stage on-device PII scrubber
python kfs_tts_enforcer.py    # Self-test Timbre v2.5 synthesis & anti-skip gate
python evaluate_pipeline.py   # Run N=60 benchmark & reproduce Tables 1 and 2
streamlit run app.py          # Launch the 3-Tab Cyber-FinTech Executive UI