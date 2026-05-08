"""iOS Settings smoke script for Device Farm.

Copy this file content into Script Management and run it on an iOS device with
automation_ready=true.
"""

app.log("iOS settings smoke start")

try:
    app.activate_app("com.apple.Preferences")
    app.wait(2)
    app.screenshot()

    source = app.source()
    assert_true(len(source) > 0, "iOS page source is empty")

    if app.has_text("通用"):
        app.click_text("通用", timeout=8)
    elif app.has_text("General"):
        app.click_text("General", timeout=8)
    else:
        app.log("General entry was not found in Settings", "WARN")

    app.wait(1)
    app.screenshot()
    app.log("iOS settings smoke passed")
    test_pass()
except Exception as exc:
    app.log(f"iOS settings smoke failed: {exc}", "ERROR")
    app.screenshot()
    test_fail(str(exc))
