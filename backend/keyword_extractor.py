import json
import os
import re
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

OPENAI_KEYWORD_MODEL_DEFAULT = "gpt-5.4-mini"
KEYWORD_PROVIDER_PRIORITY = ("openai", "gemini")

REASON_OPENAI_API_KEY_MISSING = "OPENAI_API_KEY_MISSING"
REASON_OPENAI_KEYWORD_API_FAILED = "OPENAI_KEYWORD_API_FAILED"
REASON_OPENAI_KEYWORD_SCHEMA_INVALID = "OPENAI_KEYWORD_SCHEMA_INVALID"
REASON_AI_KEYWORD_PROVIDER_UNAVAILABLE = "AI_KEYWORD_PROVIDER_UNAVAILABLE"
REASON_GEMINI_API_KEY_MISSING = "GEMINI_API_KEY_MISSING"
REASON_GEMINI_KEYWORD_API_FAILED = "GEMINI_KEYWORD_API_FAILED"


# 1. Pydantic을 이용한 데이터 구조(스키마) 정의
class ProjectAnalysis(BaseModel):
    Topic: str = Field(description="입력된 문장과 관련하여 확장된 5개의 순수 명사 키워드 (띄어쓰기로 구분, 예: 엔비디아 주식 수출 수입 경제)")


class KeywordExtractionResult(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=8)
    expanded_query: str = Field(min_length=1)
    intent: str = "public_data_search"
    domain: str = "general"
    region: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    fallback_reason: str = ""

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            token = re.sub(r"\s+", " ", str(item).strip())
            if token and token not in normalized:
                normalized.append(token)
        if not normalized:
            raise ValueError("keywords must contain at least one non-empty keyword")
        return normalized[:8]


class KeywordProviderError(Exception):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _extract_text_response(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    if isinstance(response, dict):
        if response.get("output_text"):
            return str(response["output_text"])
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message", {})
            return str(message.get("content", ""))
    return str(response)


def _parse_keyword_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _fallback_keywords(prompt: str, reason_code: str = "") -> KeywordExtractionResult:
    text = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", prompt).strip()
    tokens = [t for t in re.split(r"\s+", text) if t and t not in {"시각화", "분석", "보고", "싶어", "찾아줘", "데이터"}]
    joined = " ".join(tokens)
    expansions = {
        "집값": ["부동산", "실거래가"],
        "부동산": ["실거래가", "전월세"],
        "미세먼지": ["대기", "환경"],
        "교통량": ["도로교통", "교통"],
        "인구": ["인구통계"],
        "상권": ["소상공인", "매출"],
    }
    for key, values in expansions.items():
        if key in joined and key not in tokens:
            tokens.append(key)
        if key in joined:
            tokens.extend(values)
    deduped = []
    for token in tokens or [prompt.strip() or "공공데이터"]:
        if token and token not in deduped:
            deduped.append(token)
    region = next((r for r in ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"] if r in prompt), "")
    domain = "real_estate" if any(k in prompt for k in ["집값", "부동산", "전월세", "실거래가"]) else "general"
    return KeywordExtractionResult(
        keywords=deduped[:8],
        expanded_query=" ".join(deduped[:8]),
        intent="public_data_search",
        domain=domain,
        region=region,
        confidence=0.35,
        fallback_reason=reason_code,
    )


def extract_keywords_with_openai(user_input: str) -> KeywordExtractionResult:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise KeywordProviderError(REASON_OPENAI_API_KEY_MISSING)
    model = os.getenv("OPENAI_KEYWORD_MODEL", OPENAI_KEYWORD_MODEL_DEFAULT)
    try:
        from openai import OpenAI
    except Exception as exc:
        raise KeywordProviderError(REASON_OPENAI_KEYWORD_API_FAILED, "openai package unavailable") from exc

    prompt = f"""사용자의 자연어 입력에서 대한민국 공공데이터포털(data.go.kr) 검색에 적합한 한국어 키워드를 추출하세요.
짧은 명사구 중심으로 지역명, 도메인, 지표명을 분리하고, 설명 없이 JSON만 반환하세요.
예: 서울 집값 시각화 -> keywords [\"서울\", \"집값\", \"부동산\", \"실거래가\"], expanded_query \"서울 집값 부동산 실거래가\", domain \"real_estate\", region \"서울\".
사용자 입력: {user_input}"""
    schema = {
        "type": "object",
        "properties": {
            "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
            "expanded_query": {"type": "string"},
            "intent": {"type": "string"},
            "domain": {"type": "string"},
            "region": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "fallback_reason": {"type": "string"},
        },
        "required": ["keywords", "expanded_query", "intent", "domain", "region", "confidence", "fallback_reason"],
        "additionalProperties": False,
    }
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "keyword_extraction",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        return KeywordExtractionResult.model_validate(_parse_keyword_json(_extract_text_response(response)))
    except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise KeywordProviderError(REASON_OPENAI_KEYWORD_SCHEMA_INVALID) from exc
    except KeywordProviderError:
        raise
    except Exception as exc:
        raise KeywordProviderError(REASON_OPENAI_KEYWORD_API_FAILED) from exc


# 에러가 일시적인 API 장애(429 할당량 초과 또는 503 모델 과부하)인지 확인하는 함수
def is_retryable_error(exception: Exception) -> bool:
    error_msg = str(exception).lower()
    error_repr = repr(exception).lower()
    keywords = ["429", "resourceexhausted", "quota", "503", "unavailable", "high demand", "overloaded"]
    if any(k in error_msg or k in error_repr for k in keywords):
        return True
    code = getattr(exception, "code", None)
    status_code = getattr(exception, "status_code", None)
    return str(code) in ["429", "503"] or str(status_code) in ["429", "503"]


@retry(retry=retry_if_exception(is_retryable_error), stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=10), reraise=True)
def get_google_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다. 로컬 .env 또는 실행 환경 변수를 확인해주세요.")
    return api_key


def analyze_project_idea(user_input: str) -> ProjectAnalysis:
    get_google_api_key()
    llm = ChatGoogleGenerativeAI(model="models/gemini-3.1-flash-lite", temperature=0.2, max_retries=0)
    structured_llm = llm.with_structured_output(ProjectAnalysis)
    prompt_template = PromptTemplate.from_template(
        """당신은 키워드 추출기 입니다. 사용자가 어떤문장을 입력했을 때 그것과 관련된 키워드를 확장시켜 5개의 단어를 만들어서 추출해야됩니다.
        (예시) 사용자 입력문장 : 서울의 빈집 문제를 해결하고 싶어
        당신의 추출 키워드 : 서울특별시 빈집 주거환경 도시재생 부동산
        [중요 지시사항]
        1. Topic(주제) 필드는 절대로 서술어나 문장형식, 행동(동사)을 포함해서는 안 됩니다.
        2. 추출하는 5개의 단어는 반드시 '대한민국 공공데이터포털(data.go.kr)'에 실제 데이터셋으로 등록되어 있을 법한 공식 분류체계나 행정/공공 표준 용어로 치환/추출해야 합니다.
        3. 오직 순수 명사 키워드 5개만 띄어쓰기로 연결해서 출력하세요.
        사용자 아이디어: {user_input}
        반드시 주어진 JSON 스키마 형식에 맞춰서 답변해주세요."""
    )
    return (prompt_template | structured_llm).invoke({"user_input": user_input})


def extract_keywords_with_providers(user_input: str) -> tuple[Literal["openai", "gemini", "fallback"], KeywordExtractionResult | ProjectAnalysis, list[str]]:
    reasons: list[str] = []
    try:
        return "openai", extract_keywords_with_openai(user_input), reasons
    except KeywordProviderError as exc:
        reasons.append(exc.reason_code)

    try:
        return "gemini", analyze_project_idea(user_input), reasons
    except ValueError:
        reasons.append(REASON_GEMINI_API_KEY_MISSING)
    except Exception:
        reasons.append(REASON_GEMINI_KEYWORD_API_FAILED)

    if all(reason in {REASON_OPENAI_API_KEY_MISSING, REASON_GEMINI_API_KEY_MISSING} for reason in reasons):
        reasons.append(REASON_AI_KEYWORD_PROVIDER_UNAVAILABLE)
    return "fallback", _fallback_keywords(user_input, reasons[-1] if reasons else REASON_AI_KEYWORD_PROVIDER_UNAVAILABLE), reasons
