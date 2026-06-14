import os
import re
import unicodedata
import logging
from typing import Iterable, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_QUERY = 4000
DEFAULT_MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))


# ──────────────────────────────────────────────────────────────────────────
#  Query / output text sanitization
# ──────────────────────────────────────────────────────────────────────────

def sanitize_query(text: str) -> str:
    if text is None:
        return ""
    # remove control chars and trim
    cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:DEFAULT_MAX_QUERY]


def sanitize_output_text(text: str) -> str:
    if text is None:
        return ""
    cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", str(text))
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def clean_llm_response(text: str) -> str:
    if not text:
        return ""
    
    text = re.sub(r'Citations?:.*', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\(Source:.*?\)', ' ', text)
    text = re.sub(r',?\s*Page\s*:\s*\d+', ' ', text)
    text = re.sub(r'\b\S+\.(pdf|docx|txt|csv)\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(According to|Based on|As stated in|As per|From|The provided)\s+(the\s+)?(document|excerpt|provided|context|information)[^,\.]*[,\.]?\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(the )?(provided )?(document )?excerpts?\s+(do not|does not|state[sd]?|contain[s]?|mention[s]?|indicate[s]?)[^\.]*\.?\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'However,\s*it\s+does?\s+provide', 'It provides', text, flags=re.IGNORECASE)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def is_sensitive_request(text: str) -> bool:
    """
    Check if a user query is asking for sensitive information.
    Sensitive categories: passwords, secrets, tokens, api keys, credentials.
    """
    if not text:
        return False
    normalized = text.lower()
    SENSITIVE_PATTERNS = [
        r'\bpassword\b',
        r'\bcredential',
        r'\bapi.?key\b',
        r'\bsecret\b',
        r'\bprivate.?key\b',
        r'\btoken\b',
        r'\blogin detail',
        r'\bssh.?key\b',
        r'\bauth.?token\b',
    ]
    for term in SENSITIVE_PATTERNS:
        if re.search(term, normalized):
            return True
    return False


def detect_prompt_injection(query: str) -> bool:
    """
    Detect prompt injection attempts.
    """
    query_lower = query.lower()
    INJECTION_PATTERNS = [
        r"ignore (previous|above|all) instructions",
        r"reveal (your |the )?(system |hidden )?prompt",
        r"what (are|were) your instructions",
        r"act as (if you are|a different)",
        r"pretend (you are|to be)",
        r"jailbreak",
        r"bypass (your |the )?(rules|instructions|filters)",
        r"disregard (your |all )?(previous )?instructions",
        r"you are now",
        r"new persona",
        r"forget (your |all |previous )?instructions",
    ]
    return any(re.search(p, query_lower) for p in INJECTION_PATTERNS)


CHUNK_INJECTION_PATTERNS = [
    r"ignore (previous|above|all) instructions",
    r"reveal (your |the )?(system |hidden )?prompt",
    r"disregard",
    r"forget your instructions",
    r"you are now",
    r"new persona",
]


def sanitize_chunk(content: str) -> str:
    """
    Sanitize retrieved chunks to remove injection patterns.
    """
    for pattern in CHUNK_INJECTION_PATTERNS:
        content = re.sub(pattern, '[REDACTED]', content, flags=re.IGNORECASE)
    return content


# ──────────────────────────────────────────────────────────────────────────
#  Prompt-injection detection  (multi-layer, severity-scored)
# ──────────────────────────────────────────────────────────────────────────

# ---- Homoglyph / confusable map (Cyrillic → Latin, Greek → Latin, etc.) ----
_HOMOGLYPH_MAP = str.maketrans({
    # Cyrillic lookalikes
    '\u0430': 'a',  # а → a
    '\u0435': 'e',  # е → e
    '\u043E': 'o',  # о → o
    '\u0440': 'p',  # р → p
    '\u0441': 'c',  # с → c
    '\u0445': 'x',  # х → x
    '\u0456': 'i',  # і → i
    '\u0458': 'j',  # ј → j
    '\u04BB': 'h',  # һ → h
    '\u0501': 'd',  # ԁ → d
    '\u051B': 'q',  # ԛ → q
    '\u0455': 's',  # ѕ → s
    '\u0458': 'j',  # ј → j
    '\u0443': 'y',  # у → y
    '\u0432': 'v',  # в → v (sometimes)
    # Greek lookalikes
    '\u0391': 'A',  # Α → A
    '\u0392': 'B',  # Β → B
    '\u0395': 'E',  # Ε → E
    '\u0396': 'Z',  # Ζ → Z
    '\u0397': 'H',  # Η → H
    '\u0399': 'I',  # Ι → I
    '\u039A': 'K',  # Κ → K
    '\u039C': 'M',  # Μ → M
    '\u039D': 'N',  # Ν → N
    '\u039F': 'O',  # Ο → O
    '\u03A1': 'P',  # Ρ → P
    '\u03A4': 'T',  # Τ → T
    '\u03A5': 'Y',  # Υ → Y
    '\u03A7': 'X',  # Χ → X
    # Other confusables
    '\u0131': 'i',  # ı (dotless i) → i
    '\u0237': 'j',  # ȷ → j
    '\u1D00': 'A',  # ᴀ → A (small cap)
    '\u0299': 'B',  # ʙ → B
    '\u1D04': 'C',  # ᴄ → C
    '\u1D05': 'D',  # ᴅ → D
    '\u1D07': 'E',  # ᴇ → E
    '\u0262': 'G',  # ɢ → G
    '\u029C': 'H',  # ʜ → H
    '\u1D0A': 'J',  # ᴊ → J
    '\u1D0B': 'K',  # ᴋ → K
    '\u1D0C': 'L',  # ᴌ → L
    '\u1D0D': 'M',  # ᴍ → M
    '\u1D0F': 'O',  # ᴏ → O
    '\u1D18': 'P',  # ᴘ → P
    '\u0280': 'R',  # ʀ → R
    '\u1D1B': 'T',  # ᴛ → T
    '\u1D1C': 'U',  # ᴜ → U
    '\u1D20': 'V',  # ᴠ → V
    '\u1D21': 'W',  # ᴡ → W
    '\u028F': 'Y',  # ʏ → Y
    '\u1D22': 'Z',  # ᴢ → Z
    # Full-width Latin
    **{chr(0xFF01 + i): chr(0x21 + i) for i in range(94)},  # ！→!, ０→0 ... ～→~
})


def _normalize_for_detection(text: str) -> str:
    """Produce a normalized form that defeats common obfuscation techniques."""
    # Step 1: NFKC normalization (decomposes compatibility chars)
    text = unicodedata.normalize('NFKC', text)
    # Step 2: Strip zero-width and invisible Unicode
    text = re.sub(r'[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]', '', text)
    # Step 3: Map homoglyphs to Latin equivalents
    text = text.translate(_HOMOGLYPH_MAP)
    # Step 4: Collapse repeated characters ("iiignore" → "ignore")
    text = re.sub(r'(.)\1{3,}', r'\1\1', text)
    return text


def _detect_obfuscation(raw_text: str) -> float:
    """Return a suspicion score (0.0–1.0) for text obfuscation techniques."""
    score = 0.0
    # Zero-width characters scattered in text
    zw_count = len(re.findall(r'[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]', raw_text))
    if zw_count > 2:
        score += min(0.5, zw_count * 0.1)
    # Excessive non-ASCII ratio in an otherwise English query
    if len(raw_text) > 10:
        non_ascii = sum(1 for c in raw_text if ord(c) > 127)
        ratio = non_ascii / len(raw_text)
        if ratio > 0.3:
            score += 0.3
    # Reversed text detection (common words reversed)
    reversed_markers = ["erongi", "tsys", "tcejni", "tpircs", "drowssap", "metsys"]
    lowered = raw_text.lower()
    if any(r in lowered for r in reversed_markers):
        score += 0.4
    return min(1.0, score)


# ---- Pattern categories (all applied to normalized text) ----

# Tier 1: Critical — immediate block (weight 1.0)
_CRITICAL_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Instruction override / role hijacking
    (re.compile(r'\b(ignore|disregard|forget)\s+(all\s+|the\s+|your\s+)?(previous|prior|above|earlier|all)\s+(instructions?|prompts?|rules?|directives?|anything)\b', re.I), 'instruction_override'),
    (re.compile(r'\bhow\s+were\s+you\s+instructed\b', re.I), 'instruction_override'),
    (re.compile(r'\bhow\s+to\s+answer\s+questions\b', re.I), 'instruction_override'),
    (re.compile(r'\bforget\s+(everything|all)\s+(you\s+)?(know|knew|were\s+told)', re.I), 'instruction_override'),
    (re.compile(r'\boverride\s+(your|the|all)\s+(instructions?|rules?|guidelines?|safety)', re.I), 'instruction_override'),
    (re.compile(r'\bnew\s+instructions?\s*:', re.I), 'instruction_override'),
    (re.compile(r'\bfrom\s+now\s+on\s*,?\s*you\s+(are|will|must|shall)', re.I), 'role_hijack'),
    # Jailbreak personas
    (re.compile(r'\b(you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|become)\s+(DAN|STAN|DAN\s+mode|an?\s+?unrestricted|an?\s+?unfiltered)', re.I), 'jailbreak_persona'),
    (re.compile(r'\b(Do\s+Anything\s+Now|jailbroken|developer\s+mode\s+(on|enabled|activated))', re.I), 'jailbreak_persona'),
    (re.compile(r'\b(DAN\s+mode|enable\s+DAN|DAN\s+enabled)', re.I), 'jailbreak_persona'),
    (re.compile(r'\bact\s+as\s+if\s+you\s+have\s+no\s+(restrictions?|rules?|limitations?|guidelines?|safety)', re.I), 'jailbreak_persona'),
    (re.compile(r'\bwithout\s+(any\s+)?(restrictions?|limitations?|rules?|safety|guidelines?|filters?|censorship)', re.I), 'jailbreak_persona'),
    (re.compile(r'\b(bypass|disable)\s+(restrictions?|filters)', re.I), 'jailbreak_persona'),
    # System prompt extraction / internal info
    (re.compile(r'\b(reveal|show|output|print|display|repeat|recite|return|give|dump)\s+(your|the|my)\s+(system\s+)?(prompt|instructions?|rules?|initial\s+message|internal\s+prompt|configuration|hidden\s+instructions|chain\s+of\s+thought|reasoning|context|retrieved\s+chunks|vector\s+database|embeddings)', re.I), 'system_extraction'),
    (re.compile(r'\breveal\s+(your|the)\s+internal\s+configuration\b', re.I), 'system_extraction'),
    (re.compile(r'\bwhat\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions?|rules?|guidelines?|internal\s+prompt|configuration|hidden\s+instructions|chain\s+of\s+thought|reasoning)', re.I), 'system_extraction'),
    (re.compile(r'\b(show|reveal|give|send|dump)\s+me\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?|internal\s+prompt|configuration|hidden\s+instructions|chain\s+of\s+thought|reasoning|context|retrieved\s+chunks|vector\s+database|embeddings)', re.I), 'system_extraction'),
    (re.compile(r'\bcopy\s+and\s+paste\s+your\s+(system\s+)?(prompt|instructions?)', re.I), 'system_extraction'),
    (re.compile(r'\boutput\s+your\s+(initial|system)\s+(prompt|message|instructions?)\s+verbatim', re.I), 'system_extraction'),
    (re.compile(r'\b(reveal|show|output|print|dump)\s+your\s+initial\s+(system\s+)?(message|prompt)', re.I), 'system_extraction'),
    (re.compile(r'\b(reveal|show|output|print|dump)\s+(the\s+|your\s+)?(system\s+prompt|internal\s+prompt|hidden\s+instructions|chain\s+of\s+thought|reasoning|context|retrieved\s+chunks|vector\s+database|embeddings)', re.I), 'system_extraction'),
    (re.compile(r'\bdeveloper\s+instructions?', re.I), 'system_extraction'),
    # Data exfiltration via URL/network
    (re.compile(r'\b(send|post|fetch|request|transmit|exfiltrate|upload)\s+(the\s+|all\s+)?(data|information|content|response|answer|documents?|chunks?)\s+to\s+(https?://|an?\s+?external|a\s+?remote|my\s+?server)', re.I), 'data_exfil'),
    (re.compile(r'\b(send|post|fetch|transmit)\s+.*\bto\s+https?://', re.I), 'data_exfil'),
    (re.compile(r'\b(include|embed|insert|put|add)\s+(the\s+)?(data|information|content|response|answer|api\s*key|password|secret)\s+in\s+(a\s+)?(url|link|href|http|base64)', re.I), 'data_exfil'),
    (re.compile(r'\bbase64\s*(encode\s+)?(the\s+)?(answer|response|data|content|information)', re.I), 'data_exfil'),
    # Code execution / command injection
    (re.compile(r'\b(rm\s+-rf|sudo\s+|chmod\s+|chown\s+|mkfs\s*|dd\s+if=|/dev/(null|zero|sda|random))', re.I), 'code_exec'),
    (re.compile(r'\b(evaluate|execute|run|import|eval|exec)\s*\(.*\)', re.I), 'code_exec'),
    (re.compile(r'\b(curl|wget|nc|ncat|netcat|bash|sh|cmd|powershell|os\.system|subprocess)\b', re.I), 'code_exec'),
    (re.compile(r'\b__import__\s*\(|os\.popen\s*\(|subprocess\.\w+\s*\(', re.I), 'code_exec'),
    (re.compile(r'<\s*script[^>]*>|javascript\s*:|on\w+\s*=\s*["\']', re.I), 'code_exec'),  # XSS
    # Prompt leak via encoded output
    (re.compile(r'\bencode\s+(your|the|my)\s+(system\s+)?(prompt|instructions?|rules?|system\s+message)\s+(in|as|using)\s+(base64|rot13|hex|binary)', re.I), 'prompt_leak_encoded'),
    # Special tokens used in prompt injection (LLM-specific format strings)
    (re.compile(r'\[INST\]|<<SYS>>|<\|im_start\|>|<\|system\|>|<\|begin_of_text\|>', re.I), 'special_tokens'),
    (re.compile(r'\bIMPORTANT\s*:\s*(ignore|disregard|forget|override)', re.I), 'special_tokens'),
    # Leetspeak variants of dangerous keywords
    (re.compile(r'\b(1gn0r3|d0\s+4nyth1ng|pr3t3nd|j41lbr34k|r3v34l|3xf1ltr4t3|5yst3m\s+pr0mpt)', re.I), 'leetspeak'),
    # Multi-language injection verbs
    (re.compile(r'\b(ignorar|ignora|ignorer|ignorieren|negeren)\b', re.I), 'multilang_injection'),
    (re.compile(r'\b(olvida|dimentica|oublier|vergessen|vergeet)\s+.*(instrucciones?|istruzioni?|instructions?|règles?|regeln?)', re.I), 'multilang_injection'),
]

# Tier 2: Suspicious — contributes to score (weight 0.5)
_SUSPICIOUS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Softer instruction overrides
    (re.compile(r'\b(pretend|imagine|suppose|assume)\s+(you\s+(are|can|have)|that\s+you)', re.I), 'soft_override'),
    (re.compile(r'\byou\s+(can|may|should|must)\s+(now|also|additionally)\s+', re.I), 'soft_override'),
    (re.compile(r'\bin\s+this\s+(conversation|chat|session)\s*,?\s*you\s+(are|will|can|must)', re.I), 'soft_override'),
    # Standalone jailbreak/DAN references
    (re.compile(r'\bjailbreak\b', re.I), 'jailbreak_keyword'),
    (re.compile(r'\bDAN\b', re.I), 'dan_keyword_standalone'),
    # Developer / admin impersonation
    (re.compile(r'\b(I\s+am|I\'m)\s+(the\s+)?(admin|developer|owner|creator|system\s+admin|root)', re.I), 'impersonation'),
    (re.compile(r'\bas\s+(the\s+)?(admin|developer|owner|creator|root)\s*,?\s*(I\s+)?(command|order|instruct|tell)', re.I), 'impersonation'),
    # Output format manipulation
    (re.compile(r'\banswer\s+(in|using|with)\s+(json|xml|base64|rot13|binary|hex|markdown\s+code\s+block)', re.I), 'output_manipulation'),
    (re.compile(r'\b(wrap|enclose|put|format)\s+(your|the)\s+(answer|response|output)\s+(in|as|using)\s+(a\s+)?(url|link|href|image|img\s+tag)', re.I), 'output_manipulation'),
]

# Tier 3: Contextual — only flag when combined with other signals (weight 0.2)
_CONTEXTUAL_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bprompt\s+injection\b', re.I), 'meta_injection'),
    (re.compile(r'\b(reveal|leak|extract)\s+(the\s+)?(api\s*key|password|secret|token|credentials?)', re.I), 'secret_extraction'),
    (re.compile(r'\bstop\s+being\s+(an?\s+)?(assistant|AI|helpful|safe)', re.I), 'persona_break'),
    (re.compile(r'\bdo\s+anything\s+now\b', re.I), 'dan_keyword'),
    (re.compile(r'\bunrestricted\s+mode\b', re.I), 'dan_keyword'),
]

# Threshold: score >= this value → blocked
_INJECTION_THRESHOLD = float(os.getenv("PROMPT_INJECTION_THRESHOLD", "0.7"))


def is_suspicious_prompt(text: str) -> bool:
    """Multi-layer prompt-injection detection.

    Returns True when the text is classified as a prompt-injection attempt.
    Uses Unicode normalization, homoglyph resolution, severity-scored pattern
    matching, and obfuscation detection.
    """
    if not text:
        return False

    raw_text = text
    normalized = _normalize_for_detection(text)
    score = 0.0
    matched_categories: list = []

    # Tier 1: Critical patterns — any single match = block
    for pattern, category in _CRITICAL_PATTERNS:
        if pattern.search(normalized):
            LOGGER.warning(
                "security.prompt_injection: CRITICAL match category=%s text=%.120s",
                category, raw_text,
            )
            return True  # immediate block

    # Tier 2: Suspicious patterns — accumulate score
    for pattern, category in _SUSPICIOUS_PATTERNS:
        if pattern.search(normalized):
            score += 0.5
            matched_categories.append(category)

    # Tier 3: Contextual — light contribution
    for pattern, category in _CONTEXTUAL_KEYWORDS:
        if pattern.search(normalized):
            score += 0.2
            matched_categories.append(category)

    # Obfuscation detection — combined with even a single Tier 2 signal should block
    obfuscation_score = _detect_obfuscation(raw_text)
    score += obfuscation_score
    if obfuscation_score > 0.2:
        matched_categories.append('obfuscation')
        # Obfuscation alone is suspicious; lower effective threshold
        if score >= 0.5:
            LOGGER.warning(
                "security.prompt_injection: BLOCKED (obfuscation+signal) score=%.2f categories=%s text=%.120s",
                score, matched_categories, raw_text,
            )
            return True

    # Check threshold
    blocked = score >= _INJECTION_THRESHOLD
    if blocked:
        LOGGER.warning(
            "security.prompt_injection: BLOCKED score=%.2f categories=%s text=%.120s",
            score, matched_categories, raw_text,
        )
    elif score > 0:
        LOGGER.info(
            "security.prompt_injection: flagged score=%.2f categories=%s text=%.120s",
            score, matched_categories, raw_text,
        )
    return blocked


def scan_text_fields(fields: dict) -> Optional[str]:
    """Scan all string values in a dict for prompt injection.

    Returns the category string of the first detected injection, or None.
    Useful for scanning metadata, document content, and other indirect vectors.
    """
    for key, value in fields.items():
        if isinstance(value, str) and len(value) > 5 and is_suspicious_prompt(value):
            return key
        elif isinstance(value, dict):
            nested = scan_text_fields(value)
            if nested:
                return f"{key}.{nested}"
    return None


def validate_filename(filename: str) -> str:
    base = os.path.basename(filename or "")
    # allow only safe chars, replace others with underscore
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return safe or "upload.pdf"


def is_allowed_content_type(content_type: str, allowed: Iterable[str]) -> bool:
    if not content_type:
        return False
    return content_type.lower() in {a.lower() for a in allowed}


def max_upload_bytes() -> int:
    return DEFAULT_MAX_UPLOAD_MB * 1024 * 1024


# ──────────────────────────────────────────────────────────────────────────
#  Indirect prompt-injection defense (chunk text sanitization)
# ──────────────────────────────────────────────────────────────────────────
#
# Attackers can embed instruction-like text inside PDFs. When the RAG
# pipeline retrieves those chunks and passes them to the LLM as context,
# the LLM may follow the embedded instructions. We neutralize this by
# stripping directive patterns from chunk text before it enters the
# agent pipeline.

_INJECTED_INSTRUCTION_RE = re.compile(
    r'('
    r'(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules?|directives?)'
    r'|(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are))\s+'
    r'|(?:new\s+instructions?\s*:)'
    r'|(?:DAN|Do\s+Anything\s+Now|jailbreak|developer\s+mode)'
    r'|(?:\[INST\]|<<SYS>>|<\|im_start\|>|<\|system\|>)'
    r'|(?:IMPORTANT\s*:\s*(ignore|disregard|forget|override))'
    r')',
    re.I,
)


def sanitize_retrieved_text(text: str) -> str:
    """Strip instruction-like patterns from retrieved chunk text.

    This defends against *indirect prompt injection*: attackers embedding
    instructions inside documents that get retrieved and fed to the LLM.
    """
    if not text or not isinstance(text, str):
        return ""
    # Use both _INJECTED_INSTRUCTION_RE and CHUNK_INJECTION_PATTERNS
    cleaned = _INJECTED_INSTRUCTION_RE.sub('[REDACTED]', text)
    for pattern in CHUNK_INJECTION_PATTERNS:
        cleaned = re.sub(pattern, '[REDACTED]', cleaned, flags=re.IGNORECASE)
    if cleaned != text:
        LOGGER.warning(
            "security.indirect_injection: stripped directive patterns from chunk text (%d chars)",
            len(text) - len(cleaned),
        )
    return cleaned
