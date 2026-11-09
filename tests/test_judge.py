"""판정 규칙 단위 시험. AI 출력 대신 손으로 만든 값을 넣는다."""

from wonmun.judge import (DIFF, NEEDS_CHECK, NEITHER, NO_DIFF, NOT_IN_SUMMARY, TIME_MISSING,
                          TOP_ONLY_MISSING, build_value, judge_item)
from wonmun.quotes import QuoteIndex
from wonmun.textsrc import text_doc


def idx(role, text):
    return QuoteIndex(text_doc(text, role, "test"))


def dl(found, quotes, date="", time=""):
    return {"found": found, "quotes": quotes, "value": "", "deadline_date": date,
            "deadline_time": time, "date_role": "접수 마감"}


def run_deadline(top, body=None, orig=None):
    """top/body/orig: (원문 글, AI 출력) 또는 None"""
    vals = {}
    for role, spec in (("top", top), ("body", body), ("original", orig)):
        if spec is None:
            vals[role] = build_value("deadline", role, None, None, 2026)
        else:
            vals[role] = build_value("deadline", role, spec[1], idx(role, spec[0]), 2026)
    return judge_item("deadline", vals)


# ---------------------------------------------------------------- 마감

def test_date_differs_is_mismatch():
    r = run_deadline(
        top=("접수기간: 2026.11.02 ~ 2026.11.15", dl(True, ["접수기간: 2026.11.02 ~ 2026.11.15"], "2026-11-15")),
        orig=("접수기간: 2026. 10. 1. ~ 11. 7. 24:00", dl(True, ["접수기간: 2026. 10. 1. ~ 11. 7. 24:00"], "2026-11-07", "24:00")),
    )
    assert r["verdict"] == DIFF
    assert "8일 늦음" in r["reason"]


def test_same_day_original_time_not_2359_and_summary_no_time_is_time_missing():
    r = run_deadline(
        top=("사업 신청기간: 2026년 8월 12일 ~ 2026년 11월 6일",
             dl(True, ["2026년 8월 12일 ~ 2026년 11월 6일"], "2026-11-06")),
        orig=("접수기간 : ~ 2026. 11. 06.(금) 11:00", dl(True, ["~ 2026. 11. 06.(금) 11:00"], "2026-11-06", "11:00")),
    )
    assert r["verdict"] == TIME_MISSING


def test_original_2359_is_not_time_missing():
    r = run_deadline(
        top=("접수기간: 2026.11.01 ~ 2026.11.18", dl(True, ["2026.11.01 ~ 2026.11.18"], "2026-11-18")),
        orig=("접수: 11. 18.(수) 23:59", dl(True, ["11. 18.(수) 23:59"], "2026-11-18", "23:59")),
    )
    assert r["verdict"] == NO_DIFF


def test_original_2400_is_end_of_day_not_time_missing():
    r = run_deadline(
        top=("접수기간: 2026.11.01 ~ 2026.11.19", dl(True, ["2026.11.01 ~ 2026.11.19"], "2026-11-19")),
        orig=("11. 19.(목) 24:00까지", dl(True, ["11. 19.(목) 24:00까지"], "2026-11-19", "24:00")),
    )
    assert r["verdict"] == NO_DIFF


def test_body_has_time_gives_top_only_missing():
    r = run_deadline(
        top=("접수기간: 2026.10.26 ~ 2026.11.25", dl(True, ["2026.10.26 ~ 2026.11.25"], "2026-11-25")),
        body=("접수: 11. 25.(수) 15:00까지", dl(True, ["11. 25.(수) 15:00까지"], "2026-11-25", "15:00")),
        orig=("- 2026. 10. 26.(월) - 11. 25.(수) 15:00까지", dl(True, ["11. 25.(수) 15:00까지"], "2026-11-25", "15:00")),
    )
    assert r["verdict"] == TOP_ONLY_MISSING


def test_body_also_without_time_stays_time_missing():
    r = run_deadline(
        top=("접수기간: 2026.11.02 ~ 2026.11.30", dl(True, ["2026.11.02 ~ 2026.11.30"], "2026-11-30")),
        body=("접수 기간 11/2 ~ 11/30", dl(True, ["11/2 ~ 11/30"], "2026-11-30")),
        orig=("2026년 11월 30일(월) 17:00", dl(True, ["2026년 11월 30일(월) 17:00"], "2026-11-30", "17:00")),
    )
    assert r["verdict"] == TIME_MISSING


def test_stage1_only_without_original():
    r = run_deadline(
        top=("접수기간: 2026.08.11 ~ 2026.11.25", dl(True, ["접수기간: 2026.08.11 ~ 2026.11.25"], "2026-11-25")),
        body=("- 문제해결: 2026. 9. 15. ~ 11. 6.", dl(True, ["- 문제해결: 2026. 9. 15. ~ 11. 6."], "2026-11-06")),
    )
    assert r["verdict"] == DIFF
    assert r["stage1"]["verdict"] == DIFF
    assert "같은 페이지" in r["reason"]


def test_fabricated_quote_gives_needs_check():
    r = run_deadline(
        top=("접수기간: 2026.11.02 ~ 2026.11.15", dl(True, ["접수기간: 2026.11.02 ~ 2026.11.15"], "2026-11-15")),
        orig=("접수기간: 2026. 10. 1. ~ 11. 7. 24:00", dl(True, ["접수 마감은 11월 7일 자정"], "2026-11-07", "24:00")),
    )
    assert r["values"]["original"]["status"] == "unverified"
    assert r["verdict"] == NEEDS_CHECK


def test_model_date_not_in_quote_gives_needs_check():
    r = run_deadline(
        top=("접수기간: 2026.11.02 ~ 2026.11.15", dl(True, ["접수기간: 2026.11.02 ~ 2026.11.15"], "2026-11-15")),
        orig=("최종 발표평가 및 시상: 11. 25.", dl(True, ["최종 발표평가 및 시상: 11. 25."], "2026-11-06")),
    )
    assert r["verdict"] == NEEDS_CHECK


def test_summary_without_deadline_is_not_in_summary():
    r = run_deadline(
        top=("공고명: 무엇", dl(False, [])),
        orig=("마감 2026. 11. 7.", dl(True, ["마감 2026. 11. 7."], "2026-11-07")),
    )
    assert r["verdict"] == NOT_IN_SUMMARY


# ---------------------------------------------------------------- 자격

def el(found, quotes, open_to_all=False, applicant="알 수 없음", age_min=-1, age_max=-1,
       groups=(), region="", nationality="언급 없음", other=()):
    return {"found": found, "quotes": quotes, "value": "", "open_to_all": open_to_all,
            "applicant": applicant, "age_min": age_min, "age_max": age_max, "groups": list(groups),
            "region": region, "nationality": nationality, "other": list(other)}


def run_elig(top, body=None, orig=None):
    vals = {}
    for role, spec in (("top", top), ("body", body), ("original", orig)):
        vals[role] = (build_value("eligibility", role, None, None, 2026) if spec is None
                      else build_value("eligibility", role, spec[1], idx(role, spec[0]), 2026))
    return judge_item("eligibility", vals)


def test_open_summary_vs_restricted_original_is_mismatch():
    r = run_elig(
        top=("참여대상: 대상 제한 없음", el(True, ["참여대상: 대상 제한 없음"], open_to_all=True)),
        orig=("참가자격: 외국 국적의 클래식 전공자", el(True, ["외국 국적의 클래식 전공자"],
                                                 groups=["전공자", "외국인"], nationality="외국인")),
    )
    assert r["verdict"] == DIFF


def test_narrower_summary_is_mismatch():
    r = run_elig(
        top=("참여대상: 대학생", el(True, ["참여대상: 대학생"], groups=["대학생"])),
        orig=("만 19세 이상(고등학교 졸업 이상 학력자)", el(True, ["만 19세 이상(고등학교 졸업 이상 학력자)"],
                                                    age_min=19, groups=["고졸 이상"])),
    )
    assert r["verdict"] == DIFF
    assert "좁음" in r["reason"]


def test_both_cover_general_public_no_diff():
    r = run_elig(
        top=("참여대상: 대학생, 직장인/일반인", el(True, ["대학생, 직장인/일반인"], groups=["대학생", "직장인", "일반인"])),
        orig=("대학(원)생 · 일반인 · 스타트업", el(True, ["대학(원)생 · 일반인 · 스타트업"],
                                            groups=["대학생", "대학원생", "일반인", "창업자·스타트업"])),
    )
    assert r["verdict"] == NO_DIFF


def test_applicant_company_vs_youth_condition_is_mismatch():
    r = run_elig(
        top=("연령: 제한없음 / 취업상태: 미취업자", el(True, ["취업상태: 미취업자"], groups=["미취업자"])),
        orig=("ㅇ참여기업 대상자: 콘텐츠 기업(법인사업자)", el(True, ["참여기업 대상자: 콘텐츠 기업(법인사업자)"],
                                                     applicant="기업·기관", groups=["기업·법인"])),
    )
    assert r["verdict"] == DIFF
    assert "기업" in r["reason"]


def test_missing_age_supplied_by_body():
    r = run_elig(
        top=("참여대상: 대학생, 직장인/일반인", el(True, ["대학생, 직장인/일반인"], groups=["대학생", "직장인", "일반인"])),
        body=("만 19세 이상 39세 이하의 개인 또는 팀", el(True, ["만 19세 이상 39세 이하의 개인 또는 팀"], age_min=19, age_max=39)),
        orig=("공고일 현재 만 19세 이상 39세 이하의 개인 또는 팀", el(True, ["만 19세 이상 39세 이하의 개인 또는 팀"], age_min=19, age_max=39)),
    )
    assert r["verdict"] == TOP_ONLY_MISSING


def test_ai_age_without_evidence_is_dropped():
    r = run_elig(
        top=("참여대상: 대상 제한 없음", el(True, ["대상 제한 없음"], open_to_all=True)),
        orig=("전 국민 누구나", el(True, ["전 국민 누구나"], open_to_all=True, age_min=19)),
    )
    assert r["values"]["original"]["norm"]["age_min"] == -1
    assert r["verdict"] == NO_DIFF


def test_age_range_without_first_unit_is_read():
    # 시험용 T13: '19~39세'의 19를 못 읽어 잘못 경고하던 결함
    r = run_elig(
        top=("연령: 만 19세~만 39세", el(True, ["연령: 만 19세~만 39세"], age_min=19, age_max=39, groups=["청년"])),
        orig=("[모집 대상] 대구 19~39세 청년", el(True, ["[모집 대상] 대구 19~39세 청년"], age_min=19, age_max=39,
                                                groups=["청년"])),
    )
    assert r["values"]["original"]["norm"]["age_min"] == 19
    assert r["verdict"] == NO_DIFF


# ---------------------------------------------------------------- 시상·있음/없음 항목

def pz(found, quotes, total=0, kind="알 수 없음"):
    return {"found": found, "quotes": quotes, "value": "", "total_won": total, "kind": kind}


def test_prize_cash_looking_summary_vs_voucher_original():
    vals = {
        "top": build_value("prize", "top", pz(True, ["시상규모: 240만 원"], 2_400_000), idx("top", "시상규모: 240만 원"), 2026),
        "body": build_value("prize", "body", None, None, 2026),
        "original": build_value("prize", "original",
                                pz(True, ["240만원 규모의 시상품(모바일상품권 및 커피쿠폰 등)"], 2_400_000, "현물·상품권"),
                                idx("original", "240만원 규모의 시상품(모바일상품권 및 커피쿠폰 등)"), 2026),
    }
    assert judge_item("prize", vals)["verdict"] == DIFF


def test_prize_amount_differs():
    vals = {
        "top": build_value("prize", "top", pz(True, ["시상규모: 700만 원"], 7_000_000), idx("top", "시상규모: 700만 원"), 2026),
        "body": build_value("prize", "body", pz(True, ["상품권 총 650만원"], 6_500_000), idx("body", "상품권 총 650만원"), 2026),
        "original": build_value("prize", "original", None, None, 2026),
    }
    r = judge_item("prize", vals)
    assert r["stage1"]["verdict"] == DIFF
    assert r["verdict"] == DIFF


def pr(found, quotes):
    return {"found": found, "quotes": quotes, "value": "요약"}


def test_presence_only_in_original_is_not_in_summary():
    vals = {
        "top": build_value("ai_copyright", "top", pr(False, []), idx("top", "공고명: x"), 2026),
        "body": build_value("ai_copyright", "body", pr(False, []), idx("body", "본문"), 2026),
        "original": build_value("ai_copyright", "original", pr(True, ["생성형 AI 활용 범위를 작성"]),
                                idx("original", "□ 생성형 AI 활용 범위를 작성해야 함"), 2026),
    }
    assert judge_item("ai_copyright", vals)["verdict"] == NOT_IN_SUMMARY


def test_presence_neither():
    vals = {
        "top": build_value("penalty", "top", pr(False, []), idx("top", "x"), 2026),
        "body": build_value("penalty", "body", None, None, 2026),
        "original": build_value("penalty", "original", pr(False, []), idx("original", "y"), 2026),
    }
    assert judge_item("penalty", vals)["verdict"] == NEITHER


# ---------------------------------------------------------------- r1 이후 바꾼 규칙

def test_org_or_person_is_not_a_restriction():
    r = run_elig(
        top=("참여대상: 대상 제한 없음", el(True, ["대상 제한 없음"], open_to_all=True)),
        body=("- 문제발굴 부문: 사회·과학 당면 문제 해결이 필요한 기관 또는 개인",
              el(True, ["사회·과학 당면 문제 해결이 필요한 기관 또는 개인"], applicant="개인과 기업·기관 모두",
                 groups=["기관·단체"])),
    )
    assert r["verdict"] == NO_DIFF


def test_region_nationwide_is_not_a_condition():
    v = build_value("eligibility", "top", el(True, ["거주지역: 전국"], region="전국"),
                    idx("top", "거주지역: 전국"), 2026)
    assert v.norm["region"] == ""


def test_prize_kind_uses_whole_segment():
    text = "통합 대상 (부문 통합 1팀): 상금 1,000,000원"
    v = build_value("prize", "original", pz(True, ["1,000,000원"], 1_000_000), idx("original", text), 2026)
    assert v.norm["kind"] == "현금"


def test_reason_particles():
    r = run_deadline(
        top=("접수기간: 2026.11.02 ~ 2026.11.15", dl(True, ["접수기간: 2026.11.02 ~ 2026.11.15"], "2026-11-15")),
        orig=("접수기간: 2026. 10. 1. ~ 11. 7. 24:00", dl(True, ["접수기간: 2026. 10. 1. ~ 11. 7. 24:00"], "2026-11-07")),
    )
    assert "요약 칸이 8일 늦음" in r["reason"]


def test_stage1_contradiction_wins_over_no_diff_with_original():
    # AI가 원문에서 대회 전체 기간 끝을 마감으로 골라 칸과 같아졌더라도, 칸↔본문이 다르면 빨강
    r = run_deadline(
        top=("접수기간: 2026.08.11 ~ 2026.11.25", dl(True, ["접수기간: 2026.08.11 ~ 2026.11.25"], "2026-11-25")),
        body=("- 문제해결: 2026. 9. 15. ~ 11. 6.", dl(True, ["- 문제해결: 2026. 9. 15. ~ 11. 6."], "2026-11-06")),
        orig=("2026-08-11 ~ 2026-11-25", dl(True, ["2026-08-11 ~ 2026-11-25"], "2026-11-25")),
    )
    assert r["stage2"]["verdict"] == NO_DIFF
    assert r["verdict"] == DIFF
    assert "같은 페이지" in r["reason"]


def test_youth_label_without_age_in_summary_is_still_missing():
    # 나이 조건이 요약에 없으면 원문의 '청년'은 여전히 빠진 조건이다
    r = run_elig(
        top=("거주지역: 대구광역시", el(True, ["거주지역: 대구광역시"], region="대구광역시")),
        orig=("대구 거주 청년", el(True, ["대구 거주 청년"], groups=["청년"], region="대구")),
    )
    assert r["verdict"] == DIFF


def test_site_footer_copyright_mark_is_not_a_contest_rule():
    # 예시 L20: 밀양시 누리집 바닥글 '공공저작물 자유이용 허락표시 적용 안함'을 공모 규정으로 읽어 '요약에 없음'으로 표시했음
    foot = "공공저작물 자유이용 허락표시 적용 안함"
    ai = {"found": True, "quotes": [foot], "value": "공공저작물 자유이용 허락 미적용"}
    v = build_value("ai_copyright", "original", ai, idx("original", "접수 마감 11. 7.\n" + foot), 2026)
    assert v.status == "absent" and not v.quotes
    rule = "생성형 AI로 만든 작품은 응모할 수 없으며, 수상작의 저작권은 응모자에게 있습니다."
    v2 = build_value("ai_copyright", "original", {"found": True, "quotes": [rule], "value": "AI 금지"},
                     idx("original", rule + "\n" + foot), 2026)
    assert v2.status == "found"
