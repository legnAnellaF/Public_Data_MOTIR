import json
import os
import re
import matplotlib.pyplot as plt
import pandas as pd
import requests

# [환경 설정] 윈도우 한글 깨짐 방지
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

class IntelligentVisualizerEngine:
    """데이터 구조를 스스로 분석하여 최적의 시각화 전략을 세우고 실행하는 순수 시각화 엔진"""

    def __init__(self):
        # 공공데이터에서 시각화 가치가 높은 Y축(수치형) 핵심 키워드 가중치 사전
        self.y_priority_keywords = [
            "합계", "금액", "평가액", "주식수", "수치", "소계", 
            "값", "통행량", "이용자", "건수", "농도", "인구",
        ]

    def _load_file(self, file_path):
        """[1단계] 데이터 로드 및 결측치/헤더 정규화"""
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            else:
                df = pd.read_excel(file_path)
            
            # 헤더 탐색 및 정제 로직
            if not df.empty and len(df.columns) > 0 and isinstance(df.columns[0], (int, float)):
                df.columns = df.iloc[0]
                df = df[1:].reset_index(drop=True)
            return df
        except Exception as e:
            print(f"[ERROR] 파일 로드 실패: {e}")
            return None

    def _infer_data_types(self, df):
        """[2단계] 가로/세로 항목의 실제 데이터 형태 추론 및 문자열 정제"""
        temporal_cols = []
        numerical_cols = []
        categorical_cols = []
        
        # 제외할 키워드 (수치형이 될 수 없는 컬럼들)
        exclude_num_keywords = ["주소", "전화", "번호", "코드", "id", "명칭", "이름", "성명", "위도", "경도", "우편", "지번"]
        temporal_keywords = ["날짜", "일자", "계약일", "년월", "일시", "기간"]

        for col in df.columns:
            valid_series = df[col].dropna()
            if valid_series.empty:
                continue
                
            col_str = str(col).lower()
            
            # 1. 시계열(날짜/시간) 데이터 판별
            is_temporal = any(kw in col_str for kw in temporal_keywords)
            if not is_temporal and (valid_series.astype(str).str.contains(r"^\d{4}-\d{2}-\d{2}$|^\d{8}$").sum() / len(valid_series) > 0.5):
                is_temporal = True
                
            if is_temporal:
                temporal_cols.append(col)
                continue
                
            # 2. 명확한 범주형 배제
            if any(kw in col_str for kw in exclude_num_keywords):
                categorical_cols.append(col)
                continue

            # 3. 수치형 데이터 판별 및 단위 문자 정제 (매출, 금액 등 강제 수치화)
            sample_str = valid_series.astype(str).str.replace(r"[,\s원건명%개만천억(추정)이상미만]", "", regex=True)
            num_conv = pd.to_numeric(sample_str, errors="coerce")

            force_numeric_kws = ["매출", "금액", "비용", "인구", "점포", "단가", "수익", "수입", "수출", "합계", "통행량"]
            if num_conv.notna().sum() / len(valid_series) > 0.7 or any(kw in col_str for kw in force_numeric_kws):
                df[col] = num_conv.fillna(0)
                numerical_cols.append(col)
            else:
                categorical_cols.append(col)

        return temporal_cols, numerical_cols, categorical_cols

    def _select_optimal_axes(self, df, temporal, numerical, categorical, query=""):
        """[3단계] 맞춤형 최적의 X축과 다중 Y축 자동 선정 알고리즘"""
        final_x = None
        final_y_list = []

        invalid_y = ["번호", "순번", "id", "순위", "no", "연번", "연도"]
        valid_numerical = [col for col in numerical if not any(inv in col.lower() for inv in invalid_y)]
        
        # 도메인 키워드 룰
        startup_y_keywords = {
            "상권": ["점포", "유동인구", "매장", "상가", "영업", "폐업", "밀도", "인구"],
            "매출": ["매출", "단가", "수익", "이익", "판매", "금액", "결제"],
            "수출입": ["관세", "수출", "수입", "무역", "달러", "중량", "환율"],
            "인구": ["인구", "가구", "세대", "연령", "거주", "유동"],
            "경쟁": ["경쟁", "업체수", "점포수", "밀집도", "유사"],
            "비용": ["임대료", "권리금", "보증금", "배달비", "관리비", "비용", "단가"],
            "창업": ["매출", "유동인구", "점포", "창업", "폐업", "금액", "합계"]
        }

        # Y축 선정
        time_keywords = ["년", "월", "일", "분기", "현황", "상반기", "하반기"]
        time_cols = [col for col in valid_numerical if any(tk in str(col) for tk in time_keywords)]
        if len(time_cols) >= 2:
            final_y_list = time_cols
        else:
            if query:
                query_words = re.findall(r'[가-힣A-Za-z0-9]+', query)
                for q_word in query_words:
                    for domain, kws in startup_y_keywords.items():
                        if domain in q_word or q_word in domain or any(kw in q_word for kw in kws):
                            for col in valid_numerical:
                                if any(kw in str(col) for kw in kws) and col not in final_y_list:
                                    final_y_list.append(col)
                            if final_y_list: break
                    if final_y_list: break

            if not final_y_list:
                for kw in self.y_priority_keywords:
                    for col in valid_numerical:
                        if kw in col and col not in final_y_list:
                            final_y_list.append(col)
                        if len(final_y_list) >= 1: break
                    if len(final_y_list) >= 1: break
                if not final_y_list and valid_numerical:
                    final_y_list.append(valid_numerical[0])

        # X축 선정
        valid_categorical = [col for col in categorical if not any(inv in col.lower() for inv in invalid_y)]
        
        # 1. 상권/지역/업종 등 핵심 그룹화(X축) 키워드 우선 매칭
        x_priority_keywords = ["지역", "시도", "시군구", "상권", "업종", "구분", "명칭", "이름", "지점", "장소", "행정동", "자치구"]
        for kw in x_priority_keywords:
            for col in valid_categorical:
                if kw in str(col) and 2 <= df[col].nunique() <= 100:
                    final_x = col
                    break
            if final_x: break

        # 2. 쿼리 기반 지능형 X축 매칭
        if not final_x and query and valid_categorical:
            query_words = re.findall(r'[가-힣A-Za-z0-9]+', query)
            clean_query_words = [w.replace('별', '') for w in query_words]
            for col in valid_categorical:
                for w in clean_query_words:
                    if len(w) >= 2 and (w in str(col) or str(col) in w):
                        final_x = col
                        break
                if final_x: break

        # 3. Fallback
        if not final_x:
            if temporal: final_x = temporal[0]
            elif valid_categorical:
                for col in valid_categorical:
                    if 2 <= df[col].nunique() <= 100:
                        final_x = col
                        break
                if not final_x: final_x = valid_categorical[0]
            elif df.columns.size > 0: final_x = df.columns[0]

        return final_x, final_y_list

    def _generate_startup_precautions(self, df, x, y_list, query):
        """Generate general public-data interpretation notes for the current sample."""
        precautions = []
        scope = query.strip() if isinstance(query, str) and query.strip() else "현재 데이터"
        precautions.append(f"📌 [분석 주의사항] 현재 결과는 업로드/preview된 일부 행 기준이며, '{scope}' 맥락에서 '{x}' 기준 '{', '.join(y_list)}' 지표를 요약한 관찰값입니다.")
        precautions.append("🔎 [컬럼/단위 확인] 컬럼명과 단위가 실제 지표 의미와 일치하는지 원본 문서 또는 메타데이터로 확인해야 합니다.")
        if y_list and len(df) >= 2:
            mean_val = df[y_list[0]].mean()
            max_val = df[y_list[0]].max()
            if max_val > mean_val * 3:
                precautions.append(f"⚠️ [이상치/격차 확인] 최대값({max_val:.1f})이 평균({mean_val:.1f})의 3배 이상입니다. 누락값, 표본 범위, 집계 기준을 함께 확인하세요.")
            else:
                precautions.append("📊 [표본 범위 확인] 지역/연도별 비교 시 누락값과 표본 범위가 결과에 영향을 줄 수 있습니다.")
        precautions.append("💡 [해석 한계] 현재 결과는 원인 단정이 아니라 관찰값 요약이며, 정책·의사결정에는 원본 전체 데이터와 추가 지표 검증이 필요합니다.")
        return precautions

    def _determine_strategy_and_calculate(self, df, x, y_list, temporal_cols, query, core_keyword=""):
        """[4단계] 시각화 전략 수립 및 데이터 집계"""
        if not pd.api.types.is_numeric_dtype(df[x]):
            exclude_keywords = ['합계', '총계', '전체', '총합', '계']
            mask = ~df[x].astype(str).str.strip().isin(exclude_keywords)
            df = df[mask].copy()

        # 지역명 표준화 (상세 시군구명 완벽 보존)
        if any(kw in str(x) for kw in ['지역', '시도', '시/도', '시군구', '상권']):
            def normalize_region(val):
                val_str = str(val).strip()
                mapping = {
                    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
                    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "세종시": "세종",
                    "강원특별자치도": "강원", "전북특별자치도": "전북", "제주특별자치도": "제주"
                }
                for k, v in mapping.items():
                    if val_str.startswith(k):
                        return val_str.replace(k, v)
                return val_str
            df[x] = df[x].apply(normalize_region)

        # 데이터 집계
        summary = df.groupby(x)[y_list].sum().reset_index()
        is_temporal = x in temporal_cols or any(kw in str(x) for kw in ['년', '월', '일', '시간', '연도', '날짜', '분기'])
        
        if is_temporal:
            summary = summary.sort_values(by=x, ascending=True)
        else:
            summary = summary.sort_values(by=y_list[0], ascending=False)
            
        # 롱테일 마이너 항목 "기타" 병합
        if not is_temporal and len(summary) > 7:
            top_df = summary.iloc[:7].copy()
            others_df = summary.iloc[7:].copy()
            others_sum = others_df[y_list].sum()
            others_row = {x: "기타(Others)"}
            for y_col in y_list:
                others_row[y_col] = others_sum[y_col]
            top_df.loc[len(top_df)] = others_row
            summary = top_df

        # 차트 전략 선정
        unique_x_count = len(summary)
        chart_type = "bar"
        strategy_reason = ""
        
        if x in temporal_cols:
            chart_type = "line"
            strategy_reason = "시간 흐름 추이를 표현하기 위해 꺾은선 그래프(line)를 선택했습니다."
        elif len(y_list) >= 2:
            chart_type = "bar" # 다중 지표 시각화 최적화
            strategy_reason = "다양한 핵심 지표들을 지역/항목별로 한눈에 비교 분석하기 위해 다중 막대 그래프(bar)를 선택했습니다."
        elif unique_x_count <= 3 and len(y_list) == 1:
            chart_type = "pie"
            strategy_reason = "항목 수가 적어 전체 점유율을 한눈에 파악하기 좋은 원그래프(pie)를 선택했습니다."
        else:
            chart_type = "bar"
            strategy_reason = "항목 간의 크기 비교를 직관적으로 전달하기 위해 막대그래프(bar)를 선택했습니다."
            
        chart_title = f"'{query}' 맞춤형 {x}별 " + ", ".join(y_list) + " 분석"
        
        labels = summary[x].astype(str).tolist()
        datasets = []
        for y_col in y_list:
            data_list = summary[y_col].round(1).tolist()
            data_list = [0 if pd.isna(val) else val for val in data_list]
            datasets.append({"label": str(y_col), "data": data_list})
            
        return chart_type, chart_title, labels, datasets, strategy_reason

    def process(self, file_path, query="", core_keyword=""):
        """[5단계] 시각화 파이프라인 총괄 구동 및 아웃풋 반환"""
        df = self._load_file(file_path)
        if df is None or df.empty:
            return None

        temporal, numerical, categorical = self._infer_data_types(df)
        x, y_list = self._select_optimal_axes(df, temporal, numerical, categorical, query)
        if not x or not y_list:
            print("[ERROR] 시각화할 수 있는 유효한 숫자 데이터가 부족합니다.")
            return None

        # 시각화 결과 계산
        c_type, c_title, lbls, dsets, rsn = self._determine_strategy_and_calculate(df, x, y_list, temporal, query, core_keyword)
        
        # 테이블 데이터 생성
        table_cols = [x] + y_list
        table_df = df[table_cols].head(50).fillna("")
        
        startup_precautions = self._generate_startup_precautions(df, x, y_list, query)
        
        return {
            "status": "success",
            "chart_type": c_type,
            "chart_title": c_title,
            "labels": lbls,
            "datasets": dsets,
            "strategy_reason": rsn,
            "table_data": {"headers": [str(c) for c in table_cols], "rows": table_df.values.tolist()},
            "startup_precautions": startup_precautions
        }

# ----------------------------------------------------------
# [단독 실행 및 팀원 공유용 테스트 코드 예시]
# ----------------------------------------------------------
if __name__ == "__main__":
    # 1. 시각화 엔진 인스턴스 생성
    visualizer = IntelligentVisualizerEngine()
    
    # 2. 분석할 데이터 파일 경로 및 검색어 입력
    sample_file = "sample_dirty_startup.csv" # 분석하실 엑셀 또는 CSV 파일 경로
    search_query = "카페 창업 상권 분석"
    
    # 3. 시각화 데이터 추출 실행
    result = visualizer.process(sample_file, query=search_query)
    
    # 4. 결과 출력 (팀원 프론트엔드/백엔드 전달용 구조화 데이터)
    if result:
        print("=== 📊 시각화 분석 결과 ===")
        print(f"🔹 차트 제목: {result['chart_title']}")
        print(f"🔹 추천 차트 타입: {result['chart_type']} ({result['strategy_reason']})")
        print(f"🔹 X축 라벨: {result['labels']}")
        print(f"🔹 Y축 데이터셋: {json.dumps(result['datasets'], ensure_ascii=False, indent=2)}")
        print("\n=== 💡 AI 창업 주의사항 ===")
        for p in result['startup_precautions']:
            print(p)
