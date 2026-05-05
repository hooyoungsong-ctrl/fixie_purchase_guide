"""
픽시 자전거 가격 자동 업데이트 스크립트
GitHub Actions에서 매주 실행 — Google Gemini API + Google Search로 가격/링크 갱신
"""

import os
import re
import json
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

# ── 설정 ────────────────────────────────────────────────────
HTML_FILE  = Path("index.html")
MODEL      = "gemini-2.0-flash"          # Google Search grounding 지원 모델

TRACKED_ITEMS = [
    {
        "key":   "look_564p",
        "name":  "Look CR 564P 트랙 프레임셋",
        "query": "Look CR 564P 트랙 프레임셋 한국 가격 구매",
    },
    {
        "key":   "engine11_hyperion",
        "name":  "엔진11 하이페리온 트랙 카본 프레임셋",
        "query": "엔진11 하이페리온 카본 트랙 프레임셋 가격 구매",
    },
    {
        "key":   "rotor_aldhu",
        "name":  "Rotor ALDHU 카본 트랙 크랭크셋",
        "query": "Rotor ALDHU 트랙 크랭크셋 한국 가격 구매",
    },
    {
        "key":   "unknown_sl60",
        "name":  "Unknown SL-60 카본 픽시 휠셋",
        "query": "언노운 Unknown SL-60 카본 픽시 휠셋 가격 구매",
    },
    {
        "key":   "unknown_sl84",
        "name":  "Unknown SL-84 트랙 픽시 카본 휠셋",
        "query": "언노운 Unknown SL-84 카본 픽시 휠셋 가격 구매",
    },
]

# ── Gemini 클라이언트 ─────────────────────────────────────────
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Google Search grounding 설정
SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())
GEN_CONFIG  = types.GenerateContentConfig(
    tools=[SEARCH_TOOL],
    temperature=0.1,   # 낮을수록 일관된 JSON 출력
)


# ── 가격 검색 ────────────────────────────────────────────────
def search_price(item: dict) -> dict | None:
    """Gemini + Google Search로 부품 현재가와 구매 링크를 반환"""

    prompt = f"""한국 자전거 쇼핑몰에서 "{item['name']}"의 현재 판매가와 구매 링크를 Google 검색으로 찾아주세요.
검색어: {item['query']}

검색 결과를 바탕으로 아래 JSON 형식만 반환하세요. 다른 텍스트나 마크다운은 절대 포함하지 마세요:
{{
  "price": "가격 (예: 4,280,000원  또는  590,000–798,000원)",
  "link":  "실제 구매 가능한 URL (쇼핑몰 상품 페이지)",
  "shop":  "쇼핑몰 이름 (예: 진바이크, 고르고타고, 픽시마켓)"
}}

가격을 찾지 못한 경우에만:
{{"price": null, "link": null, "shop": null}}"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=GEN_CONFIG,
        )

        text = response.text.strip()
        # 마크다운 코드블록 제거
        text = re.sub(r"```json|```", "", text).strip()
        # JSON 오브젝트 추출
        match = re.search(r"\{[\s\S]*?\}", text)
        if not match:
            print(f"  ⚠ JSON 형식 없음. 응답: {text[:120]}")
            return None

        data = json.loads(match.group())
        if data.get("price") or data.get("link"):
            return data

    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 파싱 오류: {e}")
    except Exception as e:
        print(f"  ⚠ 오류: {type(e).__name__}: {e}")

    return None


# ── HTML 업데이트 ────────────────────────────────────────────
def update_html(results: dict[str, dict]) -> bool:
    """HTML 파일의 가격/링크/날짜를 업데이트하고 저장"""

    if not HTML_FILE.exists():
        print(f"❌ HTML 파일을 찾을 수 없습니다: {HTML_FILE}")
        return False

    html    = HTML_FILE.read_text(encoding="utf-8")
    changed = False

    for key, data in results.items():
        # 가격 업데이트
        if data.get("price"):
            new_html = re.sub(
                rf'(<div class="tier-price" id="price-{key}">)[^<]*(</div>)',
                rf'\g<1>{data["price"]}\g<2>',
                html,
            )
            if new_html != html:
                html    = new_html
                changed = True
                print(f"  ✅ [{key}] 가격: {data['price']}")

        # 링크 + 쇼핑몰명 업데이트
        if data.get("link"):
            shop_label = data.get("shop", "구매")
            new_html = re.sub(
                rf'(<a class="buy-link" id="link-{key}" href=")[^"]*(" target="_blank">)[^<]*(</a>)',
                rf'\g<1>{data["link"]}\g<2>↗ {shop_label}\g<3>',
                html,
            )
            if new_html != html:
                html    = new_html
                changed = True
                print(f"  ✅ [{key}] 링크: {shop_label} — {data['link'][:60]}...")

    # 기준일 항상 갱신
    d     = datetime.now()
    today = f"{d.year}년 {d.month}월 {d.day}일"
    new_html = re.sub(
        r'(<span id="priceDate">)[^<]*(</span>)',
        rf'\g<1>{today}\g<2>',
        html,
    )
    if new_html != html:
        html    = new_html
        changed = True
        print(f"  ✅ 기준일 업데이트: {today}")

    if changed:
        HTML_FILE.write_text(html, encoding="utf-8")
        print(f"\n✅ {HTML_FILE} 저장 완료")
    else:
        print("\n⚠ 변경된 내용 없음 (가격 동일하거나 검색 실패)")

    return changed


# ── 메인 ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("픽시 자전거 가격 자동 업데이트 (Gemini)")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"모델: {MODEL}")
    print("=" * 55)

    results: dict[str, dict] = {}
    success = 0
    fail    = 0

    for item in TRACKED_ITEMS:
        print(f"\n🔍 검색 중: {item['name']}")
        data = search_price(item)

        if data and (data.get("price") or data.get("link")):
            results[item["key"]] = data
            print(f"  → 가격: {data.get('price')}  |  쇼핑몰: {data.get('shop')}")
            success += 1
        else:
            print(f"  → 가격 정보 없음 (스킵)")
            fail += 1

    print("\n" + "-" * 55)
    print(f"검색 결과: 성공 {success}개 / 실패 {fail}개")
    print("-" * 55)

    changed = update_html(results)

    # GitHub Actions output 전달
    result_str = "changed=true" if changed else "changed=false"
    Path("update_result.txt").write_text(result_str)
    print(f"\n{result_str}")

    sys.exit(0)


if __name__ == "__main__":
    main()
