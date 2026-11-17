import time, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1280,720')
driver = webdriver.Chrome(options=opts)

try:
    file_url = 'file:///' + os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(file_url)
    time.sleep(1)

    # Click on the camera viewport on Screen 1 to open Screen 2
    cam_plate = driver.find_element(By.ID, 'recipe-live-cam-plate')
    driver.execute_script('arguments[0].click();', cam_plate)
    time.sleep(1)

    # Check that Screen 2 is active
    s2 = driver.find_element(By.ID, 'screen-cam')
    assert 'active' in s2.get_attribute('class'), "Screen 2 should be active"

    # Verify the 4 error buttons exist
    pills = driver.find_elements(By.CSS_SELECTOR, '.full-cam-error-btns .error-pill')
    print(f"Found {len(pills)} error pills on Screen 2")
    assert len(pills) == 4, f"Expected 4 error pills, found {len(pills)}"

    # Test 1: Click 0mm
    btn_0 = driver.find_element(By.CSS_SELECTOR, '.full-cam-error-btns [data-error="0mm"]')
    driver.execute_script('arguments[0].click();', btn_0)
    time.sleep(0.5)

    err_val = driver.find_element(By.ID, 'cam-error-pct-val').text.strip()
    status_badge = driver.find_element(By.ID, 'cam-error-status-badge').text.strip()
    hud_pill = driver.find_element(By.ID, 'hud-error-pill').text.strip()
    print(f"0mm Preset: err_val={err_val}, badge={status_badge}, hud={hud_pill}")
    assert '0.0' in err_val, f"Expected 0.0 in err_val, got {err_val}"
    assert 'PASS' in status_badge, f"Expected PASS in badge, got {status_badge}"

    # Take screenshot of 0mm preset
    driver.find_element(By.CLASS_NAME, 'kiosk-shell').screenshot('screen2_preset_0mm.png')

    # Test 2: Click +10mm
    btn_p10 = driver.find_element(By.CSS_SELECTOR, '.full-cam-error-btns [data-error="+10mm"]')
    driver.execute_script('arguments[0].click();', btn_p10)
    time.sleep(0.5)

    err_val = driver.find_element(By.ID, 'cam-error-pct-val').text.strip()
    status_badge = driver.find_element(By.ID, 'cam-error-status-badge').text.strip()
    hud_pill = driver.find_element(By.ID, 'hud-error-pill').text.strip()
    print(f"+10mm Preset: err_val={err_val}, badge={status_badge}, hud={hud_pill}")
    assert '+10.0' in err_val or '10.0' in err_val, f"Expected +10.0 in err_val, got {err_val}"
    assert 'FAIL' in status_badge or 'OUT OF SPEC' in status_badge, f"Expected FAIL in badge, got {status_badge}"

    # Take screenshot of +10mm preset
    driver.find_element(By.CLASS_NAME, 'kiosk-shell').screenshot('screen2_preset_plus10mm.png')

    # Test 3: Click -10mm
    btn_m10 = driver.find_element(By.CSS_SELECTOR, '.full-cam-error-btns [data-error="-10mm"]')
    driver.execute_script('arguments[0].click();', btn_m10)
    time.sleep(0.5)

    err_val = driver.find_element(By.ID, 'cam-error-pct-val').text.strip()
    status_badge = driver.find_element(By.ID, 'cam-error-status-badge').text.strip()
    hud_pill = driver.find_element(By.ID, 'hud-error-pill').text.strip()
    print(f"-10mm Preset: err_val={err_val}, badge={status_badge}, hud={hud_pill}")
    assert '-10.0' in err_val, f"Expected -10.0 in err_val, got {err_val}"
    assert 'FAIL' in status_badge or 'OUT OF SPEC' in status_badge, f"Expected FAIL in badge, got {status_badge}"

    # Take screenshot of -10mm preset
    driver.find_element(By.CLASS_NAME, 'kiosk-shell').screenshot('screen2_preset_minus10mm.png')

    # Test 4: Switch back to LIVE
    btn_live = driver.find_element(By.CSS_SELECTOR, '.full-cam-error-btns [data-error="live"]')
    driver.execute_script('arguments[0].click();', btn_live)
    time.sleep(0.5)
    print("LIVE mode successfully restored.")

    driver.find_element(By.CLASS_NAME, 'kiosk-shell').screenshot('screen2_preset_live.png')
    print("ALL TESTS PASSED!")

finally:
    driver.quit()
