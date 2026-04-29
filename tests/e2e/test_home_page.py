def test_home_page_renders(page, live_server):
    page.goto(f"{live_server.url}/")

    heading = page.get_by_role("heading", name="OPD Management System")
    health_hint = page.locator("#health-hint")

    assert heading.is_visible()
    assert health_hint.is_visible()
