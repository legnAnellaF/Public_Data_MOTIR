import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

# 1. Pydantic을 이용한 데이터 구조(스키마) 정의
# 이 모델은 LLM이 반환해야 할 정확한 JSON 구조와 필드별 제약 사항을 정의합니다.
class ProjectAnalysis(BaseModel):
    Topic: str = Field(description="입력된 문장과 관련하여 확장된 5개의 순수 명사 키워드 (띄어쓰기로 구분, 예: 엔비디아 주식 수출 수입 경제)")

# 에러가 일시적인 API 장애(429 할당량 초과 또는 503 모델 과부하)인지 확인하는 함수
def is_retryable_error(exception: Exception) -> bool:
    error_msg = str(exception).lower()
    error_repr = repr(exception).lower()
    
    # 문자열에 429나 503, 혹은 관련 키워드가 있는지 확인
    keywords = ["429", "resourceexhausted", "quota", "503", "unavailable", "high demand", "overloaded"]
    if any(k in error_msg or k in error_repr for k in keywords):
        return True
        
    # 예외 객체 내부에 status_code나 code 속성이 있는 경우 확인
    code = getattr(exception, "code", None)
    status_code = getattr(exception, "status_code", None)
    if str(code) in ["429", "503"] or str(status_code) in ["429", "503"]:
        return True
        
    return False

# 2. Tenacity를 이용한 재시도(Retry) 로직 데코레이터 적용
# 429, 503 에러 발생 시 지수 백오프(Exponential Backoff) 방식으로 재시도합니다.
# 최대 5번 재시도하며, 대기 시간은 최소 2초에서 최대 10초까지 지수적으로 증가합니다.
@retry(
    retry=retry_if_exception(is_retryable_error),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    reraise=True
)
def get_google_api_key() -> str:
    """환경 변수 또는 로컬 .env에서 Google API 키를 읽어 반환합니다."""
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다. 로컬 .env 또는 실행 환경 변수를 확인해주세요.")
    return api_key


def analyze_project_idea(user_input: str) -> ProjectAnalysis:
    """
    사용자의 아이디어를 분석하여 ProjectAnalysis 스키마에 맞는 구조화된 데이터로 반환합니다.

    이 함수가 호출될 때만 환경 변수를 확인하고 LLM API를 호출합니다.
    따라서 backend.keyword_extractor 모듈은 API 키 없이도 안전하게 import할 수 있습니다.
    """
    get_google_api_key()
    print(f"분석 진행 중: '{user_input}' ...\n")
    
    # 3. LLM 초기화 (Gemini 2.0 Flash 모델 사용)
    # 10년 차 아키텍트의 분석이므로 비교적 논리적이고 일관된 결과를 위해 temperature를 낮게(0.2) 설정합니다.
    # langchain_google_genai의 자체 재시도를 끄고(max_retries=0) 우리가 정의한 tenacity 로직을 따르게 합니다.
    llm = ChatGoogleGenerativeAI(
        model="models/gemini-3.1-flash-lite",
        temperature=0.2,
        max_retries=0
    )

    # 4. with_structured_output을 사용하여 출력 구조 강제
    # LLM이 다른 불필요한 말(마크다운 백틱 등) 없이 Pydantic 모델의 스키마 구조로만 답변을 생성하도록 보장합니다.
    structured_llm = llm.with_structured_output(ProjectAnalysis)

    # 5. 프롬프트 템플릿 정의
    prompt_template = PromptTemplate.from_template(
        """당신은 키워드 추출기 입니다. 사용자가 어떤문장을 입력했을 때 그것과 관련된 키워드를 확장시켜 5개의 단어를 만들어서 추출해야됩니다.
        (예시) 
        사용자 입력문장 : 서울의 빈집 문제를 해결하고 싶어
        당신의 추출 키워드 : 서울특별시 빈집 주거환경 도시재생 부동산

        [중요 지시사항]
        1. Topic(주제) 필드는 절대로 서술어나 문장형식, 행동(동사)을 포함해서는 안 됩니다.
        2. 추출하는 5개의 단어는 반드시 '대한민국 공공데이터포털(data.go.kr)'에 실제 데이터셋으로 등록되어 있을 법한 공식 분류체계나 행정/공공 표준 용어(예: 보건의료, 재난안전, 교통, 국토관리, 상권, 인구통계 등)로 치환/추출해야 합니다.
        3. 오직 순수 명사 키워드 5개만 띄어쓰기로 연결해서 출력하세요. (조사, 기호, AND 등 모두 제외)
        
        잘못된 예시: 무중력 운송 시스템을 개발해야 함, 반중력 운송수단 도입
        올바른 예시: 국토교통 도로교통 무인기계 항공교통 인프라

        사용자 아이디어: {user_input}

        반드시 주어진 JSON 스키마 형식에 맞춰서 답변해주세요."""
    )

    # 6. Chain 구성 및 실행
    # 프롬프트를 통해 입력값을 가공한 후, 구조화된 출력을 보장하는 LLM에 전달합니다.
    chain = prompt_template | structured_llm
    
    # LLM 호출 및 분석 실행 (여기서 API 호출이 발생합니다)
    result = chain.invoke({"user_input": user_input})
    
    return result

if __name__ == "__main__":
    print("======================================================")
    print("공공데이터 포털 키워드")
    print("======================================================")
    
    while True:
        try:
            user_input = input("\n 궁금하신 문장을 입력해주세요: ")
            
            if user_input.strip().lower() in ['q', 'quit', 'exit']:
                print("시스템을 종료합니다.")
                break
                
            if not user_input.strip():
                continue
                
            # 아이디어 분석 함수 호출
            analysis_result = analyze_project_idea(user_input)
            
            # 결과를 깔끔한 JSON 포맷으로 터미널에 출력
            print("===== [분석 결과 (JSON)] =====")
            print(analysis_result.model_dump_json(indent=4))
            
            # 추출된 키워드로 공공데이터포털 검색창 자동 실행
            import urllib.parse
            import webbrowser
            
            encoded_keywords = urllib.parse.quote(analysis_result.Topic)
            # search_url = f"https://www.data.go.kr/tcs/dss/selectDataSetList.do?dType=TOTAL&keyword={encoded_keywords}"
            search_url = f"https://www.data.go.kr/tcs/dss/selectDataSetList.do?dType=API&keyword={encoded_keywords}&detailKeyword=&publicDataPk=&recmSe=&detailText=&relatedKeyword=&commaNotInData=&commaAndData=&commaOrData=&must_not=&tabId=&dataSetCoreTf=&coreDataNm=&sort=&relRadio=&orgFullName=&orgFilter=&org=&orgSearch=&currentPage=1&perPage=10&brm=&instt=&svcType=&kwrdArray=&extsn=&coreDataNmArray=&operator=OR&pblonsipScopeCode="
            
            print(f"\n[알림] 추출된 키워드로 공공데이터포털을 브라우저에서 엽니다...")
            print(f"URL: {search_url}")
            webbrowser.open(search_url)
            
        except KeyboardInterrupt:
            print("\n시스템을 종료합니다.")
            break
        except Exception as e:
            if is_retryable_error(e):
                print("\n[에러] API 서버 지연(503) 또는 할당량 초과(429). 여러 번 재시도했으나 실패했습니다.")
                print(f"상세 에러: {e}")
            else:
                print(f"\n[예기치 않은 에러 발생] {e}")
