import os

import pytest


pytestmark = pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="RUN_E2E=1일 때만 Playwright E2E를 실행합니다.")


def test_login_page_e2e(page):
    page.goto(os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000/login"))
    page.get_by_label("아이디").fill("admin")
    page.get_by_label("비밀번호").fill(os.environ.get("E2E_ADMIN_PASSWORD", "ChangeMe!2026"))
    page.get_by_role("button", name="로그인").click()
    page.get_by_text("오늘의 내시경 일정").wait_for()

