import os
import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

# 1. Load environment variables from your .env file right at startup
load_dotenv()

GNANI_API_KEY = os.getenv("vach_1ytE2CY5X2DWTVOdopL5KADh03SlTQ5Faby05j4R3xZUiAZgkti8xrKXMMuyfwW6vPLH9zVnlcUxZhO2Ct5JRVqNTmxv6UDQ_d1c81048e4c64c118c03a5376117ea45", "")
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").lower() == "true"


class HindiNumeralNormalizer:
    """
    Deterministic converter that expands integers and decimals (0-99,99,999)
    into explicit Devanagari words so Hindi TTS never misreads decimals or commas.
    """
    _WORDS_0_TO_99 = [
        "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
        "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
        "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
        "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
        "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
        "पचास", "इकावन", "बावन", "तिरेपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
        "साठ", "इकसठ", "बासठ", "तिरेसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
        "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
        "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सतासी", "अठासी", "नवासी",
        "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे"
    ]

    @classmethod
    def int_to_hindi(cls, n: int) -> str:
        if n < 0:
            return "ऋण " + cls.int_to_hindi(-n)
        if n < 100:
            return cls._WORDS_0_TO_99[n]
        parts = []
        if n >= 100000:
            lakhs = n // 100000
            parts.append(f"{cls.int_to_hindi(lakhs)} लाख")
            n %= 100000
        if n >= 1000:
            thousands = n // 1000
            parts.append(f"{cls.int_to_hindi(thousands)} हज़ार")
            n %= 1000
        if n >= 100:
            hundreds = n // 100
            parts.append(f"{cls.int_to_hindi(hundreds)} सौ")
            n %= 100
        if n > 0:
            parts.append(cls._WORDS_0_TO_99[n])
        return " ".join(parts)

    @classmethod
    def number_to_hindi(cls, val: float | int | str) -> str:
        s = str(val).replace(",", "").strip()
        if "." in s:
            int_part, dec_part = s.split(".", 1)
            dec_part = dec_part.rstrip("0")
            if not dec_part:
                return cls.int_to_hindi(int(int_part))
            int_words = cls.int_to_hindi(int(int_part))
            # Read digits after decimal individually: e.g., .50 -> दशमलव पाँच
            dec_words = " ".join(cls._WORDS_0_TO_99[int(ch)] for ch in dec_part if ch.isdigit())
            return f"{int_words} दशमलव {dec_words}"
        return cls.int_to_hindi(int(s))

    @classmethod
    def digits_by_digit(cls, phone_str: str) -> str:
        """Reads toll-free helpline numbers digit by digit in Hindi."""
        return " ".join(cls._WORDS_0_TO_99[int(ch)] for ch in str(phone_str) if ch.isdigit())


class KFSTemplateBuilder:
    """
    Builds the non-identifying RBI Key Facts Statement (KFS) Hindi read-back string
    strictly from verified bank payload fields. Zero customer PII is ever included.
    """
    @staticmethod
    def build_kfs_text(sanction_payload: Dict[str, Any]) -> str:
        tenure_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload["tenure_months"])
        apr_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload["apr_pct"])
        fee_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload["proc_fee_inr"])
        emi_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload["emi_inr"])
        total_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload["total_repayment_inr"])
        cool_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload.get("cooling_off_days", 3))
        helpline_w = HindiNumeralNormalizer.digits_by_digit(
            sanction_payload.get("grievance_helpline", "1800112233")
        )

        is_ins_mandatory = bool(sanction_payload.get("insurance_mandatory", False))

        if not is_ins_mandatory:
            return (
                f"कृपया हस्ताक्षर करने से पहले मुख्य तथ्य विवरण ध्यान से सुनें: "
                f"आपके ऋण की अवधि {tenure_w} महीने है, वार्षिक प्रतिशत दर यानी एपीआर {apr_w} प्रतिशत है, "
                f"और एकमुश्त प्रोसेसिंग शुल्क {fee_w} रुपये है। "
                f"आपकी मासिक किस्त {emi_w} रुपये होगी, और पूरी अवधि में आपको कुल {total_w} रुपये चुकाने होंगे। "
                f"इस ऋण के साथ कोई भी बीमा योजना लेना अनिवार्य नहीं है। "
                f"ऋण स्वीकृत होने के बाद आपको {cool_w} दिन का कूलिंग-ऑफ समय मिलेगा, "
                f"जिसमें आप बिना किसी अतिरिक्त जुर्माने के ऋण रद्द कर सकते हैं। "
                f"किसी भी शिकायत के लिए हमारे टोल-फ्री नंबर {helpline_w} पर संपर्क करें।"
            )
        else:
            ins_w = HindiNumeralNormalizer.number_to_hindi(sanction_payload.get("ins_prem_inr", 0))
            return (
                f"कृपया हस्ताक्षर करने से पहले मुख्य तथ्य विवरण ध्यान से सुनें: "
                f"आपके ऋण की अवधि {tenure_w} महीने है। "
                f"इसमें {ins_w} रुपये का क्रेडिट-लाइफ बीमा प्रीमियम और {fee_w} रुपये का प्रोसेसिंग शुल्क शामिल है, "
                f"जिन्हें मिलाकर आपकी कुल प्रभावी वार्षिक प्रतिशत दर यानी एपीआर {apr_w} प्रतिशत है। "
                f"आपकी मासिक किस्त {emi_w} रुपये होगी, और पूरी अवधि में आपको कुल {total_w} रुपये चुकाने होंगे। "
                f"ऋण स्वीकृत होने के बाद आपको {cool_w} दिन का कूलिंग-ऑफ समय मिलेगा, "
                f"जिसमें आप ऋण रद्द कर सकते हैं। "
                f"किसी भी शिकायत के लिए हमारे टोल-फ्री नंबर {helpline_w} पर संपर्क करें।"
            )


class GnaniTimbreEnforcer:
    """
    Handles offline cache lookup, Gnani Timbre v2.5 synthesis (SDK + REST fallback),
    and the cryptographic playback-completion lock before customer signature.
    """
    TTS_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"

    def __init__(self, cache_dir: str = "tts_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.signature_unlocked = False
        self.audit_receipt: Optional[Dict[str, Any]] = None

    def synthesize_or_get_cached(
        self, kfs_text: str, voice: str = "Nalini", model: str = "timbre-v2.5", language: str = "hi-IN"
    ) -> Tuple[Path, str]:
        """
        Checks local disk cache first (saves API credits & works offline in villages).
        If not cached, calls Gnani Timbre v2.5 via SDK or REST API.
        """
        template_hash = hashlib.sha256(f"{model}|{voice}|{language}|{kfs_text}".encode("utf-8")).hexdigest()
        wav_path = self.cache_dir / f"kfs_{template_hash[:16]}.wav"

        if wav_path.exists() and wav_path.stat().st_size > 0:
            print(f"[Cache Hit] Playing pre-cached offline KFS audio: {wav_path.name} (0 credits used)")
            return wav_path, template_hash

        if DRY_RUN_MODE or not GNANI_API_KEY or GNANI_API_KEY == "paste_your_gnani_api_key_here":
            print("[Dry-Run Mode] Generating local mock WAV header (set GNANI_API_KEY in .env for live TTS).")
            wav_path.write_bytes(b"RIFF_MOCK_WAV_AUDIO_BYTES")
            return wav_path, template_hash

        # Method A: Try official gnani-vachana Python SDK first
        try:
            from gnani.tts import GnaniTTSClient, AudioConfig
            client = GnaniTTSClient(api_key=GNANI_API_KEY)
            audio_bytes = client.synthesize(
                text=kfs_text,
                voice=voice,
                model=model,
                language=language,
                audio_config=AudioConfig(
                    sample_rate=48000,
                    encoding="linear_pcm",
                    container="wav",
                ),
            )
            wav_path.write_bytes(audio_bytes)
            print(f"[Gnani SDK] Synthesized & cached {wav_path.name}")
            return wav_path, template_hash
        except ImportError:
            pass

        # Method B: Direct REST call to https://api.vachana.ai/api/v1/tts/inference
        headers = {
            "X-API-Key-ID": GNANI_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": kfs_text,
            "voice": voice,
            "model": model,
            "language": language,
            "speed": 1.0,
            "audio_config": {
                "sample_rate": 48000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        resp = requests.post(self.TTS_REST_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        wav_path.write_bytes(resp.content)
        print(f"[Gnani REST API] Synthesized & cached {wav_path.name} ({len(resp.content)} bytes)")
        return wav_path, template_hash

    def verify_playback_completion(
        self, template_hash: str, started_at: float, completed_at: float, expected_min_duration_sec: float = 12.0
    ) -> Dict[str, Any]:
        """
        Enforces Fix 3: The customer signature / biometric button stays LOCKED
        unless playback duration >= expected_min_duration_sec (preventing skipping).
        """
        actual_duration = round(completed_at - started_at, 2)
        if actual_duration < expected_min_duration_sec:
            self.signature_unlocked = False
            raise PermissionError(
                f"SECURITY LOCK: KFS playback skipped or aborted early "
                f"({actual_duration}s < {expected_min_duration_sec}s). Biometric consent stays DISABLED."
            )

        self.signature_unlocked = True
        self.audit_receipt = {
            "kfs_template_sha256": template_hash,
            "playback_started_epoch": round(started_at, 3),
            "playback_completed_epoch": round(completed_at, 3),
            "verified_duration_sec": actual_duration,
            "signature_gate_status": "UNLOCKED_AFTER_FULL_PLAYBACK",
        }
        return self.audit_receipt


# ==============================================================================
# SELF-TEST: Run `python kfs_tts_enforcer.py`
# ==============================================================================
if __name__ == "__main__":
    # Sample Verified Bank Sanction Payload (Contains zero PII)
    sample_sanction = {
        "tenure_months": 24,
        "apr_pct": 18.5,
        "proc_fee_inr": 500,
        "emi_inr": 1250,
        "total_repayment_inr": 30000,
        "insurance_mandatory": False,
        "ins_prem_inr": 0,
        "cooling_off_days": 3,
        "grievance_helpline": "1800112233",
    }

    kfs_hindi_text = KFSTemplateBuilder.build_kfs_text(sample_sanction)
    print("=== 1. VERIFIED NON-PII HINDI KFS READ-BACK TEXT ===")
    print(kfs_hindi_text)

    enforcer = GnaniTimbreEnforcer()
    wav_file, tpl_hash = enforcer.synthesize_or_get_cached(kfs_hindi_text)

    print("\n=== 2. TESTING ANTI-SKIP SIGNATURE GATE ===")
    t_start = time.time()
    try:
        # Simulate an agent trying to skip after 2 seconds
        enforcer.verify_playback_completion(tpl_hash, t_start, t_start + 2.0, expected_min_duration_sec=12.0)
    except PermissionError as err:
        print(f"  [Blocked as expected]: {err}")

    # Simulate full playback completion
    receipt = enforcer.verify_playback_completion(tpl_hash, t_start, t_start + 14.5, expected_min_duration_sec=12.0)
    print(f"  [Unlocked after full playback]:\n  {json.dumps(receipt, indent=2)}")