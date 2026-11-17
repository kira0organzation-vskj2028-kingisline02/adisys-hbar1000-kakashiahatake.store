import subprocess
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

server_proc = subprocess.Popen(
    [sys.executable, "-u", "server.py", "--port", "11199"],
    env=dict(os.environ, FBARX_SIM="1")
)
time.sleep(2.5)

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1280,720')
opts.add_argument('--ignore-certificate-errors')

driver = webdriver.Chrome(options=opts)
passed = []
failed = []

def record(test_name, condition, err_msg=""):
    if condition:
        print(f"  [PASS] {test_name}", flush=True)
        passed.append(test_name)
    else:
        print(f"  [FAIL] {test_name}: {err_msg}", flush=True)
        failed.append(f"{test_name}: {err_msg}")

try:
    print("Connecting to http://127.0.0.1:11199/...", flush=True)
    driver.get("http://127.0.0.1:11199/")
    time.sleep(3.0)

    # ----------------------------------------------------
    # 1. Page reload / Initial state: Everything in OFF state
    # ----------------------------------------------------
    print("\n--- 1. Testing Page Reload / Initial OFF State ---", flush=True)
    stn1_off_active = driver.find_element(By.CSS_SELECTOR, '#col-stn1 [data-mode="OFF"]').get_attribute('class')
    stn2_off_active = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="OFF"]').get_attribute('class')
    record("STN 1 starts in OFF mode", "active" in stn1_off_active)
    record("STN 2 starts in OFF mode", "active" in stn2_off_active)

    off_overlay = driver.find_element(By.ID, 'live-cam-off-overlay')
    live_cam_img = driver.find_element(By.ID, 'recipe-live-cam-img')
    record("Camera off-overlay is visible on boot", off_overlay.is_displayed())
    record("Camera img is hidden on boot", not live_cam_img.is_displayed())

    # ----------------------------------------------------
    # 2. Camera strictly follows STN 2, NOT STN 1
    # ----------------------------------------------------
    print("\n--- 2. Testing Camera Scope (STN 2 only, NOT STN 1) ---", flush=True)
    stn1_auto = driver.find_element(By.CSS_SELECTOR, '#col-stn1 [data-mode="AUTO"]')
    stn1_auto.click()
    time.sleep(0.5)
    record("STN 1 in AUTO mode does NOT show camera feed when STN 2 is OFF", off_overlay.is_displayed() and not live_cam_img.is_displayed())

    stn1_man = driver.find_element(By.CSS_SELECTOR, '#col-stn1 [data-mode="MAN"]')
    stn1_man.click()
    time.sleep(0.5)
    record("STN 1 in MAN mode does NOT show camera feed when STN 2 is OFF", off_overlay.is_displayed() and not live_cam_img.is_displayed())

    # ----------------------------------------------------
    # 3. Camera window displays in STN 2 MAN and AUTO mode
    # ----------------------------------------------------
    print("\n--- 3. Testing Camera Window Display in STN 2 MAN & AUTO ---", flush=True)
    stn2_man = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="MAN"]')
    stn2_man.click()
    time.sleep(1.0)
    record("Camera off-overlay hidden in STN 2 MAN mode", not off_overlay.is_displayed())
    record("Camera live img displayed in STN 2 MAN mode", live_cam_img.is_displayed())

    stn2_auto = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="AUTO"]')
    stn2_auto.click()
    time.sleep(1.0)
    record("Camera off-overlay hidden in STN 2 AUTO mode", not off_overlay.is_displayed())
    record("Camera live img displayed in STN 2 AUTO mode", live_cam_img.is_displayed())

    stn2_off = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="OFF"]')
    stn2_off.click()
    time.sleep(1.0)
    record("Camera off-overlay shown when STN 2 returns to OFF", off_overlay.is_displayed())
    record("Camera live img hidden when STN 2 returns to OFF", not live_cam_img.is_displayed())

    # ----------------------------------------------------
    # 4. Stepper Decrement (Minus) in MAN Mode Decreases Output
    # ----------------------------------------------------
    print("\n--- 4. Testing Stepper Decrement in MAN Mode (Both Stations) ---", flush=True)
    # STN 2 MAN mode
    stn2_man.click()
    time.sleep(0.5)
    stn2_bar_txt = driver.find_element(By.ID, 'stn2-out-bar-txt')
    initial_stn2_val = float(stn2_bar_txt.text.replace('%', ''))
    record("STN 2 in MAN mode initialized to non-zero output (>=50%)", initial_stn2_val >= 50.0, f"Got {initial_stn2_val}")

    stn2_down = driver.find_element(By.ID, 'stn2-step-down')
    stn2_down.click()
    time.sleep(0.4)
    after_down_stn2 = float(stn2_bar_txt.text.replace('%', ''))
    record("STN 2 minus button decreases output", after_down_stn2 < initial_stn2_val, f"Before: {initial_stn2_val}, After: {after_down_stn2}")

    stn2_down.click()
    time.sleep(0.4)
    after_down_stn2_2 = float(stn2_bar_txt.text.replace('%', ''))
    record("STN 2 second minus button decreases output further", after_down_stn2_2 < after_down_stn2, f"Before: {after_down_stn2}, After: {after_down_stn2_2}")

    # STN 1 MAN mode
    stn1_bar_txt = driver.find_element(By.ID, 'stn1-out-bar-txt')
    initial_stn1_val = float(stn1_bar_txt.text.replace('%', ''))
    record("STN 1 in MAN mode initialized to non-zero output (>=50%)", initial_stn1_val >= 50.0, f"Got {initial_stn1_val}")

    stn1_down = driver.find_element(By.ID, 'stn1-step-down')
    stn1_down.click()
    time.sleep(0.4)
    after_down_stn1 = float(stn1_bar_txt.text.replace('%', ''))
    record("STN 1 minus button decreases output", after_down_stn1 < initial_stn1_val, f"Before: {initial_stn1_val}, After: {after_down_stn1}")

    # ----------------------------------------------------
    # 5. STN 1 Calibration Cancel Closes Screen Completely
    # ----------------------------------------------------
    print("\n--- 5. Testing STN 1 Calibration Cancel Button ---", flush=True)
    cal_btn = driver.find_element(By.ID, 'btn-stn1-cal')
    cal_btn.click()
    time.sleep(0.5)

    numpad_modal = driver.find_element(By.ID, 'numpad-modal')
    stn1_cal_screen = driver.find_element(By.ID, 'stn1-cal-screen')
    stn1_control_screen = driver.find_element(By.ID, 'stn1-control-screen')

    record("Numpad opened on CALIBRATE click", numpad_modal.is_displayed())
    record("STN 1 Cal Screen opened", stn1_cal_screen.is_displayed())

    cancel_btn = driver.find_element(By.ID, 'numpad-btn-cancel')
    cancel_btn.click()
    time.sleep(0.5)

    record("Numpad closed on CANCEL click", not numpad_modal.is_displayed())
    record("STN 1 Cal Screen closed completely on CANCEL", not stn1_cal_screen.is_displayed())
    record("Control Parameters screen is NOT showing", not stn1_control_screen.is_displayed())

    # ----------------------------------------------------
    # 6. Smooth Bar Transitions CSS
    # ----------------------------------------------------
    print("\n--- 6. Testing Smooth Bar Transitions CSS ---", flush=True)
    bar1 = driver.find_element(By.ID, 'stn1-out-bar')
    bar2 = driver.find_element(By.ID, 'stn2-out-bar')
    t1 = bar1.value_of_css_property('transition')
    t2 = bar2.value_of_css_property('transition')
    record("STN 1 bar has smooth transition", "0.3s" in t1 or "cubic-bezier" in t1 or "width" in t1, f"Transition: {t1}")
    record("STN 2 bar has smooth transition", "0.3s" in t2 or "cubic-bezier" in t2 or "width" in t2, f"Transition: {t2}")

    # ----------------------------------------------------
    # 7. STN 1 Output Numpad Input & Reflection
    # ----------------------------------------------------
    print("\n--- 7. Testing STN 1 Output Numpad Typing & Reflection ---", flush=True)
    stn1_out_symbol = driver.find_element(By.CSS_SELECTOR, '#col-stn1 [data-output-pad="stn1"]')
    stn1_out_symbol.click()
    time.sleep(0.5)
    record("STN 1 Output Numpad opens", numpad_modal.is_displayed())

    # Type 4, 2, ., 5 -> 42.5
    for key in ['4', '2', '.', '5']:
        k_btn = driver.find_element(By.CSS_SELECTOR, f'#numpad-modal .num-key[data-k="{key}"]')
        k_btn.click()
        time.sleep(0.05)

    ok_btn = driver.find_element(By.ID, 'numpad-btn-ok')
    ok_btn.click()
    time.sleep(0.6)

    stn1_new_txt = driver.find_element(By.ID, 'stn1-out-bar-txt').text
    record("STN 1 bar reflects entered value (42.5%)", "42.5" in stn1_new_txt, f"Got: {stn1_new_txt}")

finally:
    driver.quit()
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except:
        server_proc.kill()

print("\n==========================================")
print(f" TOTAL TESTS: {len(passed) + len(failed)}")
print(f" PASSED: {len(passed)}")
print(f" FAILED: {len(failed)}")
print("==========================================")
if failed:
    sys.exit(1)
