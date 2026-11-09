import os
import re
import sys
import time
import warnings
from typing import Dict, List, Tuple, Optional

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification


class LocalRAMVault:
    """
    Stores reversible token mappings {<TOKEN_ID>: "Original Value"} strictly
    in volatile local device memory. Never serialized to cloud APIs.
    """
    def __init__(self) -> None:
        self._forward_map: Dict[str, str] = {}
        self._reverse_map: Dict[str, str] = {}
        self._counters: Dict[str, int] = {}

    def store(self, category: str, raw_value: str, metadata: Optional[str] = None) -> str:
        cleaned = raw_value.strip()
        if cleaned in self._forward_map:
            return self._forward_map[cleaned]

        idx = self._counters.get(category, 0) + 1
        self._counters[category] = idx
        suffix = f"_{metadata}" if metadata else ""
        token = f"<{category}{suffix}_{idx}>"

        self._forward_map[cleaned] = token
        self._reverse_map[token] = cleaned
        return token

    def detokenize(self, text: str) -> str:
        restored = text
        for token in sorted(self._reverse_map.keys(), key=len, reverse=True):
            restored = restored.replace(token, self._reverse_map[token])
        return restored

    def clear(self) -> None:
        self._forward_map.clear()
        self._reverse_map.clear()
        self._counters.clear()


class VerhoeffChecksum:
    _d = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    _p = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 8, 5],
    ]

    @classmethod
    def validate(cls, num_str: str) -> bool:
        digits = re.sub(r"\D", "", num_str)
        if len(digits) != 12 or not digits.isdigit():
            return False
        c = 0
        for i, ch in enumerate(reversed(digits)):
            c = cls._d[c][cls._p[i % 8][int(ch)]]
        return c == 0


class HighRecallPIIScrubber:
    WORD_TO_DIGIT: Dict[str, str] = {
        "शून्य": "0", "जीरो": "0", "ज़ीरो": "0", "shunya": "0", "zero": "0",
        "एक": "1", "ek": "1", "one": "1",
        "दो": "2", "do": "2", "two": "2",
        "तीन": "3", "teen": "3", "three": "3",
        "चार": "4", "chaar": "4", "char": "4", "four": "4",
        "पाँच": "5", "पांच": "5", "paanch": "5", "panch": "5", "five": "5",
        "छह": "6", "छः": "6", "chhah": "6", "cheh": "6", "six": "6",
        "सात": "7", "saat": "7", "seven": "7",
        "आठ": "8", "aath": "8", "eight": "8",
        "नौ": "9", "nau": "9", "nine": "9",
    }

    MULTIPLIERS: Dict[str, int] = {
        "डबल": 2, "double": 2,
        "ट्रिपल": 3, "triple": 3,
    }

    FILLER_WORDS = {"अह", "उम", "जी", "हाँ", "हा", "uh", "um", "ji", "haan"}

    def __init__(
        self,
        load_ner_model: bool = True,
        model_name: str = "Babelscape/wikineural-multilingual-ner",
    ) -> None:
        self.load_ner_model = load_ner_model
        self.tokenizer = None
        self.ner_model = None

        if self.load_ner_model:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                base_model = AutoModelForTokenClassification.from_pretrained(model_name)
                base_model.eval()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.ner_model = torch.ao.quantization.quantize_dynamic(
                        base_model, {torch.nn.Linear}, dtype=torch.qint8
                    )
            except Exception as exc:
                print(f"[Warning] Could not load {model_name} ({exc}). Falling back to cue NER.")
                self.load_ner_model = False

        self.re_upi = re.compile(r"\b[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z]{2,32}\b")
        self.re_pan = re.compile(r"\b[A-Z]{5}\s*[0-9]{4}\s*[A-Z]\b", re.IGNORECASE)
        self.re_ifsc = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE)
        self.re_dob = re.compile(
            r"\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|(?:जन्म\s*तिथि|DOB|date\s*of\s*birth)\s*[:\-]?\s*\d{1,2}\s*\w+\s*\d{2,4})\b",
            re.IGNORECASE,
        )
        self.re_long_digits = re.compile(r"(?<!\d)(?:\d[\s\-]*){9,18}(?!\d)")
        self.re_context_secret = re.compile(
            r"((?:ओटीपी|OTP|पिन|PIN|कोड|code|पासवर्ड|अंतिम\s*चार\s*अंक|last\s*4\s*digits)[^\d]{0,25})(\b\d{4,8}\b)",
            re.IGNORECASE,
        )

        _hindi_stop = r"(?!(?:है|हैं|हूँ|हो|था|थी|थे|से|को|का|की|के|ने|में|पर|और|बोल|जी)\b)"

        self.re_name_cues = re.compile(
            rf"((?:मेरा\s*नाम|नाम|मैं\s*हूँ|ग्राहक|पेशेंट|मरीज|श्रीमती|श्री|सुश्री|patient|customer|name\s*is)\s+)"
            rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}}|{_hindi_stop}[\u0900-\u097F]+(?:\s+{_hindi_stop}[\u0900-\u097F]+){{0,2}})",
            re.IGNORECASE,
        )
        self.re_loc_cues = re.compile(
            rf"((?:गाँव|गांव|ग्राम|मैं|रहने\s*वाला|मोहल्ला|तहसील|जिला|village|ward)\s+)"
            rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|{_hindi_stop}[\u0900-\u097F]+(?:\s+{_hindi_stop}[\u0900-\u097F]+)?)",
            re.IGNORECASE,
        )

    def normalize_spoken_numbers_windowed(self, utterances: List[str], window_size: int = 3) -> str:
        combined = " ".join(u.strip() for u in utterances if u.strip())
        tokens = combined.split()
        out_tokens: List[str] = []

        i = 0
        while i < len(tokens):
            clean_tok = re.sub(r"[,\.\!\?;:]", "", tokens[i]).lower()

            if clean_tok in self.MULTIPLIERS and (i + 1) < len(tokens):
                next_clean = re.sub(r"[,\.\!\?;:]", "", tokens[i + 1]).lower()
                if next_clean in self.WORD_TO_DIGIT:
                    out_tokens.append(self.WORD_TO_DIGIT[next_clean] * self.MULTIPLIERS[clean_tok])
                    i += 2
                    continue
                elif next_clean.isdigit() and len(next_clean) == 1:
                    out_tokens.append(next_clean * self.MULTIPLIERS[clean_tok])
                    i += 2
                    continue

            if clean_tok in self.WORD_TO_DIGIT:
                out_tokens.append(self.WORD_TO_DIGIT[clean_tok])
                i += 1
                continue

            if clean_tok in self.FILLER_WORDS and out_tokens and out_tokens[-1].isdigit():
                if (i + 1) < len(tokens):
                    peek = re.sub(r"[,\.\!\?;:]", "", tokens[i + 1]).lower()
                    if peek in self.WORD_TO_DIGIT or peek in self.MULTIPLIERS or peek.isdigit():
                        i += 1
                        continue

            out_tokens.append(tokens[i])
            i += 1

        merged_tokens: List[str] = []
        digit_buffer: List[str] = []

        for tok in out_tokens:
            stripped = re.sub(r"[\-]", "", tok)
            if stripped.isdigit() and len(stripped) <= 4:
                digit_buffer.append(stripped)
            else:
                if digit_buffer:
                    total_digits = "".join(digit_buffer)
                    if len(total_digits) >= 4:
                        merged_tokens.append(total_digits)
                    else:
                        merged_tokens.extend(digit_buffer)
                    digit_buffer = []
                merged_tokens.append(tok)

        if digit_buffer:
            total_digits = "".join(digit_buffer)
            if len(total_digits) >= 4:
                merged_tokens.append(total_digits)
            else:
                merged_tokens.extend(digit_buffer)

        return " ".join(merged_tokens)

    def _run_transformer_ner(self, text: str, vault: LocalRAMVault) -> str:
        def _mask_name_cue(match: re.Match) -> str:
            prefix, name_val = match.group(1), match.group(2)
            if "<" in name_val:
                return match.group(0)
            return prefix + vault.store("PERSON", name_val)

        def _mask_loc_cue(match: re.Match) -> str:
            prefix, loc_val = match.group(1), match.group(2)
            if "<" in loc_val:
                return match.group(0)
            return prefix + vault.store("LOC", loc_val)

        text = self.re_name_cues.sub(_mask_name_cue, text)
        text = self.re_loc_cues.sub(_mask_loc_cue, text)

        if self.load_ner_model and self.tokenizer is not None and self.ner_model is not None:
            inputs = self.tokenizer(
                text, return_tensors="pt", truncation=True, max_length=512, return_offsets_mapping=True
            )
            offsets = inputs.pop("offset_mapping")[0].tolist()
            with torch.no_grad():
                logits = self.ner_model(**inputs).logits
            preds = torch.argmax(logits, dim=-1)[0].tolist()
            id2label = self.ner_model.config.id2label

            spans: List[Tuple[int, int, str]] = []
            cur_start, cur_end, cur_type = None, None, None

            for (start, end), pred_id in zip(offsets, preds):
                if start == end:
                    continue
                label = id2label.get(pred_id, "O")
                if label.startswith("B-"):
                    if cur_start is not None:
                        spans.append((cur_start, cur_end, cur_type))
                    cur_start, cur_end, cur_type = start, end, label[2:]
                elif label.startswith("I-") and cur_type == label[2:]:
                    cur_end = end
                else:
                    if cur_start is not None:
                        spans.append((cur_start, cur_end, cur_type))
                        cur_start, cur_end, cur_type = None, None, None
            if cur_start is not None:
                spans.append((cur_start, cur_end, cur_type))

            for start, end, ent_type in reversed(spans):
                surface = text[start:end].strip()
                if not surface or "<" in surface or ">" in surface or surface.isdigit():
                    continue
                if surface in {"है", "हैं", "हूँ", "से", "को", "का", "की", "के", "ने", "में", "पर"}:
                    continue
                if ent_type in ("PER", "PERSON"):
                    tok = vault.store("PERSON", surface)
                    text = text[:start] + tok + text[end:]
                elif ent_type in ("LOC", "LOCATION", "GPE"):
                    tok = vault.store("LOC", surface)
                    text = text[:start] + tok + text[end:]

        return text

    def scrub_transcript(
        self, utterances_or_text: List[str] | str, vault: Optional[LocalRAMVault] = None
    ) -> Tuple[str, LocalRAMVault, Dict[str, float]]:
        t0 = time.perf_counter()
        if vault is None:
            vault = LocalRAMVault()

        if isinstance(utterances_or_text, str):
            utterances = [s for s in re.split(r"(?<=[।\.!\?])\s+", utterances_or_text) if s]
        else:
            utterances = utterances_or_text

        normalized_text = self.normalize_spoken_numbers_windowed(utterances)

        normalized_text = self.re_upi.sub(
            lambda m: vault.store("UPI_REDACTED", m.group(0)), normalized_text
        )
        normalized_text = self.re_pan.sub(
            lambda m: vault.store("PAN_REDACTED", m.group(0)), normalized_text
        )
        normalized_text = self.re_ifsc.sub(
            lambda m: vault.store("IFSC_REDACTED", m.group(0)), normalized_text
        )
        normalized_text = self.re_dob.sub(
            lambda m: vault.store("DOB_REDACTED", m.group(0)), normalized_text
        )

        def _mask_long_digits(match: re.Match) -> str:
            raw_seq = match.group(0)
            digits_only = re.sub(r"\D", "", raw_seq)
            if not (9 <= len(digits_only) <= 18):
                return raw_seq

            meta = f"{len(digits_only)}D"
            if len(digits_only) == 12:
                is_verhoeff = VerhoeffChecksum.validate(digits_only)
                meta = "12D_CHK_PASS" if is_verhoeff else "12D_CHK_ANY"
            elif len(digits_only) == 10:
                meta = "10D_PHONE_OR_ACCT"
            elif len(digits_only) == 16:
                meta = "16D_CARD_OR_VID"

            trailing = " " if raw_seq.endswith(" ") else ""
            return vault.store("ID_OR_ACCT_REDACTED", raw_seq.strip(), metadata=meta) + trailing

        normalized_text = self.re_long_digits.sub(_mask_long_digits, normalized_text)

        def _mask_secret(match: re.Match) -> str:
            prefix, code = match.group(1), match.group(2)
            return prefix + vault.store("SECRET_CODE_REDACTED", code)

        normalized_text = self.re_context_secret.sub(_mask_secret, normalized_text)
        scrubbed_text = self._run_transformer_ner(normalized_text, vault)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        metrics = {
            "latency_ms": round(latency_ms, 2),
            "entities_redacted": len(vault._reverse_map),
        }
        return scrubbed_text, vault, metrics