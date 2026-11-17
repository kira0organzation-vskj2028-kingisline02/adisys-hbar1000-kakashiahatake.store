import subprocess
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

server_proc = subprocess.Popen(
    [sys.executable, "server.py", "--port", "11198"],
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
    print("Connecting to http://127.0.0.1:11198/...")
    driver.get("http://127.0.0.1:11198/")
    time.sleep(3.0)

    # ==========================================
    # TEST 1: CAMERA OPENING & CLOSING IN ALL MODES
    # ==========================================
    print("\n--- 1. Testing Camera Opening & Closing in All Modes ---")
    live_plate = driver.find_element('id', 'recipe-live-cam-plate')
    cam_screen = driver.find_element('id', 'screen-cam')
    stn_screen = driver.find_element('id', 'screen-stn')
    btn_cam_home = driver.find_element('id', 'btn-cam-return-home')
    stn2_off = driver.find_element('css selector', '#col-stn2 [data-mode="OFF"]')
    stn2_man = driver.find_element('css selector', '#col-stn2 [data-mode="MAN"]')
    stn2_auto = driver.find_element('css selector', '#col-stn2 [data-mode="AUTO"]')

    # 1.1 In OFF Mode
    stn2_off.click()
    time.sleep(0.5)
    live_plate.click()
    time.sleep(0.8)
    badge = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens in OFF Mode", 'active' in cam_screen.get_attribute('class') and 'STANDBY' in badge)
    btn_cam_home.click()
    time.sleep(0.5)
    record("Camera Closes in OFF Mode", 'active' in stn_screen.get_attribute('class') and 'active' not in cam_screen.get_attribute('class'))

    # 1.2 In MAN Mode
    stn2_man.click()
    time.sleep(0.5)
    live_plate.click()
    time.sleep(0.8)
    badge = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens in MAN Mode", 'active' in cam_screen.get_attribute('class') and 'MAN' in badge)
    btn_cam_home.click()
    time.sleep(0.5)
    record("Camera Closes in MAN Mode", 'active' in stn_screen.get_attribute('class') and 'active' not in cam_screen.get_attribute('class'))

    # 1.3 In AUTO Mode
    stn2_auto.click()
    time.sleep(0.5)
    live_plate.click()
    time.sleep(0.8)
    badge = driver.find_element('id', 'full-cam-mode-badge').text
    record("Camera Opens in AUTO Mode", 'active' in cam_screen.get_attribute('class') and 'AUTO' in badge)
    btn_cam_home.click()
    time.sleep(0.5)
    record("Camera Closes in AUTO Mode", 'active' in stn_screen.get_attribute('class') and 'active' not in cam_screen.get_attribute('class'))

    # ==========================================
    # TEST 2: NUMPAD DISMISSAL ON MODE SWITCH
    # ==========================================
    print("\n--- 2. Testing Numpad Dismissal on Mode Switch ---")
    stn1_man = driver.find_element('css selector', '#col-stn1 [data-mode="MAN"]')
    stn1_auto = driver.find_element('css selector', '#col-stn1 [data-mode="AUTO"]')
    stn1_off = driver.find_element('css selector', '#col-stn1 [data-mode="OFF"]')
    numpad = driver.find_element('id', 'numpad-modal')

    # 2.1 Open STN 1 S-Tension Numpad in MAN mode, then switch to AUTO
    stn1_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'stn1-stension-box').click()
    time.sleep(0.5)
    record("Numpad Opens for S-Tension in MAN", 'open' in numpad.get_attribute('class'))

    # Trigger mode change to AUTO
    driver.execute_script("arguments[0].click();", stn1_auto)
    time.sleep(0.5)
    record("Numpad Dismissed When Switching STN 1 to AUTO", 'open' not in numpad.get_attribute('class'))

    # 2.2 Open STN 1 S-Tension Numpad in MAN mode, then switch to OFF
    stn1_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'stn1-stension-box').click()
    time.sleep(0.5)
    record("Numpad Opens for S-Tension in MAN again", 'open' in numpad.get_attribute('class'))

    driver.execute_script("arguments[0].click();", stn1_off)
    time.sleep(0.5)
    record("Numpad Dismissed When Switching STN 1 to OFF", 'open' not in numpad.get_attribute('class'))

    # 2.3 Open STN 2 Repeat Length Numpad in MAN mode, then switch to AUTO
    stn2_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'tile-repeat-length').click()
    time.sleep(0.5)
    record("Numpad Opens for Repeat Length in MAN", 'open' in numpad.get_attribute('class'))

    driver.execute_script("arguments[0].click();", stn2_auto)
    time.sleep(0.5)
    record("Numpad Dismissed When Switching STN 2 to AUTO", 'open' not in numpad.get_attribute('class'))

    # 2.4 Open STN 2 Mark Window Numpad in MAN mode, then switch to OFF
    stn2_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'tile-mark-window').click()
    time.sleep(0.5)
    record("Numpad Opens for Mark Window in MAN", 'open' in numpad.get_attribute('class'))

    driver.execute_script("arguments[0].click();", stn2_off)
    time.sleep(0.5)
    record("Numpad Dismissed When Switching STN 2 to OFF", 'open' not in numpad.get_attribute('class'))

    # 2.5 Backdrop click dismissal
    stn2_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'tile-repeat-length').click()
    time.sleep(0.5)
    record("Numpad Opens Before Backdrop Click", 'open' in numpad.get_attribute('class'))
    # Click overlay directly (e.g. top corner 10, 10)
    driver.execute_script("document.getElementById('numpad-modal').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));")
    time.sleep(0.5)
    record("Numpad Dismissed on Backdrop Overlay Click", 'open' not in numpad.get_attribute('class'))

    # ==========================================
    # TEST 3: VISUAL INTEGRITY - NO BLEED-THROUGH
    # ==========================================
    print("\n--- 3. Testing Visual Integrity & Stacking Context ---")
    stn2_man.click()
    time.sleep(0.5)
    driver.find_element('id', 'stn2-out-row').click()
    time.sleep(0.5)
    record("Numpad Opens for STN 2 Output", 'open' in numpad.get_attribute('class'))

    # Take screenshot of the open numpad to verify NO mode buttons bleed through
    driver.save_screenshot('C:/Users/Admin/.gemini/antigravity/brain/c822483c-07f0-4930-a0f0-6eb6fb130cb4/numpad_clean_view.png')
    
    # Check that modal overlay z-index is higher than any mode button
    overlay_z = int(driver.execute_script("return window.getComputedStyle(document.getElementById('numpad-modal')).zIndex") or 0)
    raw_strip_z = driver.execute_script("return window.getComputedStyle(document.querySelector('.mode-selector-strip')).zIndex")
    mode_strip_z = 0 if (not raw_strip_z or raw_strip_z == 'auto') else int(raw_strip_z)
    record("Modal Overlay sits strictly ABOVE mode buttons", overlay_z > mode_strip_z, f"overlay z={overlay_z}, strip z={mode_strip_z}")

    # Close numpad
    driver.find_element('id', 'numpad-btn-cancel').click()
    time.sleep(0.5)
    record("Numpad Closes on Cancel Button", 'open' not in numpad.get_attribute('class'))

    # ==========================================
    # TEST 4: RECIPE BUTTONS & INTERACTIONS
    # ==========================================
    print("\n--- 4. Testing Recipe Buttons ---")
    # 4.1 Open Recipe Screen from RECIPE button
    btn_recipe = driver.find_element('id', 'btn-load-slaves')
    btn_recipe.click()
    time.sleep(0.8)
    recipe_screen = driver.find_element('id', 'recipe-load-screen')
    record("Recipe Screen Opens from #btn-load-slaves", 'open' in recipe_screen.get_attribute('class'))

    # 4.2 Recipe dropdown selection changes recipe
    sel_name = driver.find_element('id', 'recipe-select-name')
    options = sel_name.find_elements('tag name', 'option')
    record("Recipe Select Has Options", len(options) > 1, f"Found {len(options)} options")

    # 4.3 Recipe Camera Open/Close button in recipe screen
    btn_cam_open = driver.find_element('id', 'recipe-camera-open')
    btn_cam_open.click()
    time.sleep(0.5)
    cam_status = driver.find_element('id', 'recipe-camera-status').text
    record("Recipe Camera Opens", 'LIVE' in cam_status or 'ON' in cam_status, f"status: {cam_status}")

    btn_cam_open.click()
    time.sleep(0.5)
    cam_status_closed = driver.find_element('id', 'recipe-camera-status').text
    record("Recipe Camera Closes", 'OFF' in cam_status_closed, f"status: {cam_status_closed}")

    # 4.4 Close Recipe Screen via Home button
    btn_recipe_home = driver.find_element('id', 'recipe-load-home')
    btn_recipe_home.click()
    time.sleep(0.5)
    record("Recipe Screen Closes Cleanly via Home", 'open' not in recipe_screen.get_attribute('class'))

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
