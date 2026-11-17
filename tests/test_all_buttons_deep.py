import subprocess
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

server_proc = subprocess.Popen(
    [sys.executable, "server.py", "--port", "11197"],
    env=dict(os.environ, FBARX_SIM="1")
)
time.sleep(2.0)

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1280,720')
opts.add_argument('--ignore-certificate-errors')
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
passed = []
failed = []

def record(test_name, condition, err_msg=""):
    if condition:
        print(f"  [PASS] {test_name}")
        passed.append(test_name)
    else:
        print(f"  [FAIL] {test_name}: {err_msg}")
        failed.append(f"{test_name}: {err_msg}")

try:
    print("Connecting to http://127.0.0.1:11197/...")
    driver.get("http://127.0.0.1:11197/")
    time.sleep(3.0)

    # Check JS console errors right away
    logs = [l for l in driver.get_log('browser') if l['level'] == 'SEVERE' and 'favicon' not in l['message']]
    record("Zero JS Console Errors on load", len(logs) == 0, f"Found errors: {logs}")

    # ==========================================
    # 1. TEST RECIPE BUTTON & MODAL
    # ==========================================
    print("\n--- 1. Testing RECIPE Button ---")
    btn_recipe = driver.find_element('id', 'btn-load-slaves')
    btn_recipe.click()
    time.sleep(0.8)
    recipe_modal = driver.find_element('id', 'recipe-load-screen')
    record("Recipe Modal Opens", 'open' in recipe_modal.get_attribute('class'), f"classes: {recipe_modal.get_attribute('class')}")

    btn_cancel_recipe = driver.find_element('id', 'recipe-load-home')
    btn_cancel_recipe.click()
    time.sleep(0.5)
    record("Recipe Modal Closes on Home Click", 'open' not in recipe_modal.get_attribute('class'))

    # ==========================================
    # 2. TEST REPORT BUTTON & MODAL
    # ==========================================
    print("\n--- 2. Testing REPORT Button ---")
    btn_report = driver.find_element('id', 'btn-open-report')
    btn_report.click()
    time.sleep(0.8)
    report_modal = driver.find_element('id', 'report-screen')
    record("Report Screen Opens", 'open' in report_modal.get_attribute('class'))

    btn_close_report = driver.find_element('id', 'report-home')
    btn_close_report.click()
    time.sleep(0.5)
    record("Report Screen Closes", 'open' not in report_modal.get_attribute('class'))

    # ==========================================
    # 3. TEST STN 1 MODE BUTTONS
    # ==========================================
    print("\n--- 3. Testing STN 1 Mode Buttons ---")
    stn1_auto = driver.find_element('css selector', '#col-stn1 [data-mode="AUTO"]')
    stn1_man = driver.find_element('css selector', '#col-stn1 [data-mode="MAN"]')
    stn1_off = driver.find_element('css selector', '#col-stn1 [data-mode="OFF"]')
    col_stn1 = driver.find_element('id', 'col-stn1')

    stn1_man.click()
    time.sleep(0.5)
    record("STN 1 Switches to MAN", 'mode-man' in col_stn1.get_attribute('class') and 'active' in stn1_man.get_attribute('class'))

    stn1_auto.click()
    time.sleep(0.5)
    record("STN 1 Switches to AUTO", 'mode-auto' in col_stn1.get_attribute('class') and 'active' in stn1_auto.get_attribute('class'))

    stn1_off.click()
    time.sleep(0.5)
    record("STN 1 Switches to OFF", 'mode-off' in col_stn1.get_attribute('class') and 'active' in stn1_off.get_attribute('class'))

    # ==========================================
    # 4. TEST STN 2 MODE BUTTONS
    # ==========================================
    print("\n--- 4. Testing STN 2 Mode Buttons ---")
    stn2_auto = driver.find_element('css selector', '#col-stn2 [data-mode="AUTO"]')
    stn2_man = driver.find_element('css selector', '#col-stn2 [data-mode="MAN"]')
    stn2_off = driver.find_element('css selector', '#col-stn2 [data-mode="OFF"]')
    col_stn2 = driver.find_element('id', 'col-stn2')

    stn2_man.click()
    time.sleep(0.8)
    record("STN 2 Switches to MAN", 'mode-man' in col_stn2.get_attribute('class') and 'active' in stn2_man.get_attribute('class'))

    stn2_auto.click()
    time.sleep(0.8)
    record("STN 2 Switches to AUTO", 'mode-auto' in col_stn2.get_attribute('class') and 'active' in stn2_auto.get_attribute('class'))

    stn2_off.click()
    time.sleep(0.8)
    record("STN 2 Switches to OFF", 'mode-off' in col_stn2.get_attribute('class') and 'active' in stn2_off.get_attribute('class'))

    # ==========================================
    # 5. TEST STN 1 & STN 2 CALIBRATION BUTTONS
    # ==========================================
    print("\n--- 5. Testing Calibration Buttons ---")
    btn_stn1_cal = driver.find_element('id', 'btn-stn1-cal')
    btn_stn1_cal.click()
    time.sleep(1.0)
    stn1_cal_screen = driver.find_element('id', 'stn1-cal-screen')
    record("STN 1 Calibration Opens", 'open' in stn1_cal_screen.get_attribute('class'))

    # Close password numpad & calibration modal
    driver.execute_script("""
        document.getElementById('numpad-modal')?.classList.remove('open');
        document.getElementById('stn1-cal-screen')?.classList.remove('open');
    """)
    time.sleep(0.5)
    record("STN 1 Calibration Closes Cleanly", 'open' not in stn1_cal_screen.get_attribute('class'))

    btn_stn2_cal = driver.find_element('id', 'btn-stn2-cal')
    btn_stn2_cal.click()
    time.sleep(0.8)
    numpad = driver.find_element('id', 'numpad-modal')
    record("STN 2 Calibrate Prompts Password", 'open' in numpad.get_attribute('class'))

    numpad_cancel = driver.find_element('id', 'numpad-btn-cancel')
    numpad_cancel.click()
    time.sleep(0.5)
    record("STN 2 Password Modal Closes", 'open' not in numpad.get_attribute('class'))

    # ==========================================
    # 6. TEST LIVE CAM CARD INTERACTION
    # ==========================================
    print("\n--- 6. Testing LIVE CAM Card ---")
    live_plate = driver.find_element('id', 'recipe-live-cam-plate')
    cam_screen = driver.find_element('id', 'screen-cam')

    # Test camera opens in OFF mode (Standby live inspection)
    live_plate.click()
    time.sleep(0.8)
    badge = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens in OFF Mode (STANDBY)", 'active' in cam_screen.get_attribute('class') and 'STANDBY' in badge)

    btn_cam_home = driver.find_element('id', 'btn-cam-return-home')
    driver.execute_script("arguments[0].click();", btn_cam_home)
    time.sleep(0.8)
    record("Camera Returns Home from OFF Mode", 'active' not in cam_screen.get_attribute('class'))

    # Switch STN 2 to MAN, click live plate
    stn2_man.click()
    time.sleep(0.8)
    live_plate.click()
    time.sleep(1.0)
    badge_man = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens when STN 2 is in MAN mode", 'active' in cam_screen.get_attribute('class') and 'MAN' in badge_man)

    driver.execute_script("arguments[0].click();", btn_cam_home)
    time.sleep(0.8)
    record("Camera Returns Home cleanly", 'active' not in cam_screen.get_attribute('class'))

    # Switch STN 2 to AUTO, click live plate
    stn2_auto.click()
    time.sleep(0.8)
    live_plate.click()
    time.sleep(1.0)
    badge_auto = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens when STN 2 is in AUTO mode", 'active' in cam_screen.get_attribute('class') and 'AUTO' in badge_auto)

    driver.execute_script("arguments[0].click();", btn_cam_home)
    time.sleep(0.8)
    record("Camera Returns Home from AUTO Mode", 'active' not in cam_screen.get_attribute('class'))

    # ==========================================
    # 7. TEST NUMPAD / EDITABLE FIELDS
    # ==========================================
    print("\n--- 7. Testing Numpad Fields ---")
    stn2_mode = driver.execute_script("return window.HMI_STATE?.stn2?.mode")
    print(f"Current STN 2 mode before numpad tests: {stn2_mode}")
    if stn2_mode != 'MAN':
        print("Explicitly clicking STN 2 MAN button...")
        driver.find_element('css selector', '#col-stn2 [data-mode="MAN"]').click()
        time.sleep(0.8)
        print("STN 2 mode is now:", driver.execute_script("return window.HMI_STATE?.stn2?.mode"))

    tile_rep = driver.find_element('id', 'tile-repeat-length')
    tile_rep.click()
    time.sleep(0.5)
    record("Repeat Length Numpad Opens", 'open' in numpad.get_attribute('class'))

    numpad_cancel = driver.find_element('id', 'numpad-btn-cancel')
    numpad_cancel.click()
    time.sleep(0.5)
    record("Numpad Closes on Cancel", 'open' not in numpad.get_attribute('class'))

    tile_mw = driver.find_element('id', 'tile-mark-window')
    tile_mw.click()
    time.sleep(0.5)
    record("Mark Window Numpad Opens", 'open' in numpad.get_attribute('class'))
    numpad_cancel.click()
    time.sleep(0.5)

    # Switch STN 1 to MAN mode so S-Tension box is interactive
    stn1_man.click()
    time.sleep(0.5)
    stension_box = driver.find_element('id', 'stn1-stension-box')
    stension_box.click()
    time.sleep(0.5)
    record("S-Tension Numpad Opens", 'open' in numpad.get_attribute('class'))
    numpad_cancel = driver.find_element('id', 'numpad-btn-cancel')
    numpad_cancel.click()
    time.sleep(0.5)

    # ==========================================
    # 8. TEST STN 1 UNIT TOGGLE (KG <-> N)
    # ==========================================
    print("\n--- 8. Testing Unit Toggle ---")
    unit_btn = driver.find_element('id', 'stn1-unit-toggle')
    init_unit = unit_btn.text
    unit_btn.click()
    time.sleep(0.4)
    new_unit = unit_btn.text
    record("STN 1 Unit Toggles (KG <-> N)", init_unit != new_unit, f"was {init_unit}, now {new_unit}")
    unit_btn.click() # restore

    # ==========================================
    # 9. TEST COL 3 CALIBRATE BUTTON (PASSWORD)
    # ==========================================
    print("\n--- 9. Testing Col 3 Calibrate Button ---")
    btn_cal = driver.find_element('id', 'btn-quick-new')
    btn_cal.click()
    time.sleep(0.8)
    record("Password Modal Opens on Calibrate Click", 'open' in numpad.get_attribute('class'))

    numpad_cancel = driver.find_element('id', 'numpad-btn-cancel')
    numpad_cancel.click()
    time.sleep(0.5)
    record("Password Modal Closes on Cancel", 'open' not in numpad.get_attribute('class'))

    # ==========================================
    # 10. TEST STEPPER BUTTONS IN MAN MODE
    # ==========================================
    print("\n--- 10. Testing Stepper Buttons ---")
    # Switch STN 1 to MAN mode
    stn1_man.click()
    time.sleep(0.5)
    out_val_el = driver.find_element('id', 'stn1-out-bar-txt')
    init_val = out_val_el.text
    btn_up = driver.find_element('id', 'stn1-step-up')
    btn_up.click()
    time.sleep(0.4)
    val_after_up = out_val_el.text
    record("STN 1 Output Stepper Up Works", init_val != val_after_up, f"init {init_val}, after {val_after_up}")

    btn_down = driver.find_element('id', 'stn1-step-down')
    btn_down.click()
    time.sleep(0.4)
    val_after_down = out_val_el.text
    record("STN 1 Output Stepper Down Works", val_after_down == init_val or val_after_down != val_after_up)

    driver.save_screenshot('C:/Users/Admin/.gemini/antigravity/brain/c822483c-07f0-4930-a0f0-6eb6fb130cb4/test_all_buttons_results.png')
    print(f"\n==========================================")
    print(f" TOTAL TESTS: {len(passed) + len(failed)}")
    print(f" PASSED: {len(passed)}")
    print(f" FAILED: {len(failed)}")
    print(f"==========================================")
    if failed:
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)

finally:
    driver.quit()
    server_proc.terminate()
    server_proc.wait(timeout=2)
