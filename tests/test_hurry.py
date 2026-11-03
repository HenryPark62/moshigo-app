"""자유식 시간에 맞춘 메뉴 고르기: 남은 시간 계산."""
from core import freemeal


def test_leave_by_subtracts_walk_and_buffer():
    # 12:10에 70분 남음, 돌아오는 데 8분, 10분 미리 -> 13:02에 나서야 한다
    assert freemeal.leave_by("12:10", 70, 8, 10) == 13 * 60 + 2
    assert freemeal.leave_by(12 * 60 + 10, 70, 8, 10) == 13 * 60 + 2


def test_leave_by_past_midnight():
    # 23:20에 65분 남음(00:25 모임), 5분 걷고 10분 미리 -> 다음 날 00:10
    until = freemeal.leave_by("23:20", 65, 5, 10)
    assert until == 24 * 60 + 10


def test_time_left_same_day():
    assert freemeal.time_left(13 * 60 + 2, 12 * 60 + 22) == 40
    assert freemeal.time_left(13 * 60, 13 * 60) == 0


def test_time_left_past_midnight():
    until = 24 * 60 + 10  # 다음 날 00:10
    assert freemeal.time_left(until, 23 * 60 + 50) == 20  # 아직 자정 전
    assert freemeal.time_left(until, 5) == 5  # 자정을 넘긴 뒤 (00:05)
    assert freemeal.time_left(until, 20) == -10  # 00:20, 이미 지남


def test_time_left_already_passed():
    assert freemeal.time_left(13 * 60, 13 * 60 + 15) == -15
    assert freemeal.time_left(23 * 60 + 50, 10) == -20  # 23:50이 지나 00:10


def test_dish_fits():
    assert freemeal.dish_fits(10, 40)  # 10 + 25 = 35
    assert freemeal.dish_fits(15, 40)  # 40, 딱 맞음
    assert not freemeal.dish_fits(20, 40)
    assert not freemeal.dish_fits(5, 0)
    assert freemeal.dish_fits(None, 30)
    assert freemeal.dish_fits(20, 30, eat_min=10)
