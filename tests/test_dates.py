from datetime import date

import pytest

from wonmun.dates import all_points, parse_dates, read_deadline, standalone_times


def one(text, ref_year=2026):
    ms = parse_dates(text, ref_year)
    assert len(ms) == 1, ms
    return ms[0]


def test_full_dotted_with_weekday_and_time():
    m = one("접수기간 : ~ 2026. 11. 06.(금) 11:00 / 인원 초과시 모집 조기종료")
    assert m.end.date == date(2026, 11, 6)
    assert m.end.time == "11:00"
    assert m.is_range and m.start is None  # '~'로 시작하는 기간


def test_korean_month_day_with_time():
    m = one("접수 마감: 11월 30일(월) 17:00", ref_year=2026)
    assert m.end.date == date(2026, 11, 30)
    assert m.end.time == "17:00"
    assert m.end.year_given is False


def test_apostrophe_year_range_with_fullwidth_tilde():
    m = one("3차 원서접수 '26.11.5.(목)∼11.19.(목)")
    assert m.is_range
    assert m.start.date == date(2026, 11, 5)
    assert m.end.date == date(2026, 11, 19)


def test_24_00_is_end_of_day():
    m = one("접수기간: 2026. 10. 1. ~ 11. 7. 24:00")
    assert m.start.date == date(2026, 10, 1)
    assert m.end.date == date(2026, 11, 7)
    assert m.end.time == "24:00"
    assert m.end.end_of_day


def test_short_md_after_tilde():
    m = one("접수기간 ~11.25", ref_year=2026)
    assert m.end.date == date(2026, 11, 25)
    assert m.is_range


def test_full_range_dotted():
    m = one("접수기간: 2026.08.11 ~ 2026.11.25")
    assert m.start.date == date(2026, 8, 11)
    assert m.end.date == date(2026, 11, 25)
    assert m.end.time is None


def test_korean_full_range():
    m = one("사업 신청기간: 2026년 8월 12일 ~ 2026년 11월 6일")
    assert (m.start.date, m.end.date) == (date(2026, 8, 12), date(2026, 11, 6))


def test_dotted_md_range_inherits_year():
    m = one("- 문제해결: 2026. 9. 15. ~ 11. 6.")
    assert m.end.date == date(2026, 11, 6)


def test_pm_hour_korean():
    m = one("11월 20일(금) 오후 6시까지", ref_year=2026)
    assert m.end.time == "18:00"


def test_pm_colon_time():
    m = one("2026.11.30 오후 5:00 마감")
    assert m.end.time == "17:00"


def test_midnight_word():
    m = one("11. 22.(일)(자정까지 신청서·영상 제출)", ref_year=2026)
    assert m.end.date == date(2026, 11, 22)
    assert m.end.time == "24:00"


def test_hyphen_range_with_time():
    m = one("- 2026. 10. 26.(월) - 11. 25.(수) 15:00까지")
    assert m.end.date == date(2026, 11, 25)
    assert m.end.time == "15:00"


def test_iso_like_with_seconds():
    m = one("recruitCloseAt 2026-11-30 23:59:59")
    assert m.end.time == "23:59"


def test_year_rollover_in_range():
    m = one("2026. 12. 15. ~ 1. 10.")
    assert m.end.date == date(2027, 1, 10)


@pytest.mark.parametrize("text", [
    "총 상금 1,300만원 / 11개 팀 선발",
    "평점 3.5점 이상",
    "1080x1920 해상도, 30초~60초",
    "문의 02-123-4567",
    "공고 제2026-0885호",
    "파일 1.5배 크기",
    "A4 10매 내외",
])
def test_no_false_dates(text):
    assert parse_dates(text, 2026) == []


def test_two_dates_in_one_line():
    pts = all_points("문제발굴: 8. 11. ~ 9. 4. / 문제해결: 9. 15. ~ 11. 6.", 2026)
    assert [p.date for p in pts] == [date(2026, 8, 11), date(2026, 9, 4), date(2026, 9, 15), date(2026, 11, 6)]


def test_standalone_times():
    assert standalone_times("제출 마감 당일 23:59까지") == ["23:59"]
    assert standalone_times("오후 6시") == ["18:00"]


# ---------------------------------------------------------------- read_deadline

def test_read_deadline_accepts_model_date_in_quote_and_uses_code_time():
    r = read_deadline(["접수기간 : ~ 2026. 11. 06.(금) 11:00"], "2026-11-06", "", 2026)
    assert r.verified and r.date == date(2026, 11, 6) and r.time == "11:00"


def test_read_deadline_rejects_date_not_in_quote():
    r = read_deadline(["최종 발표평가 및 시상: 11. 25."], "2026-11-06", "", 2026)
    assert not r.verified


def test_read_deadline_picks_matching_point_among_many():
    r = read_deadline(["- 문제해결: 9. 15. ~ 11. 6."], "2026-11-06", "", 2026)
    assert r.verified and r.date == date(2026, 11, 6) and r.time is None


def test_read_deadline_model_time_only_if_written():
    q = ["문제 해결 09.15 ~ 11.06", "제출 마감 당일 23:59"]
    assert read_deadline(q, "2026-11-06", "23:59", 2026).time == "23:59"
    assert read_deadline(q[:1], "2026-11-06", "23:59", 2026).time is None  # 인용에 없는 시각은 안 씀


def test_read_deadline_without_model_date_takes_latest_end():
    r = read_deadline(["접수기간: 2026.08.11 ~ 2026.11.25"], "", "", 2026)
    assert r.date == date(2026, 11, 25)


def test_same_day_time_range_takes_end_time():
    # 시험용 R1: 시작 시각 10:00을 마감으로 읽던 결함
    m = one("접수: 12. 02(수) 10:00~17:30 (방문 접수)")
    assert m.end.date == date(2026, 12, 2)
    assert m.end.time == "17:30"


def test_date_range_with_times_keeps_both_ends():
    m = one("4. 접수기간: 2026. 11. 9.(월) 10:00 ~ 11. 13.(금) 16:00")
    assert m.start.time == "10:00"
    assert m.end.date == date(2026, 11, 13) and m.end.time == "16:00"
