import subprocess
import time
import sys
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

TEST_PORT = 11205
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

server_proc = subprocess.Popen(
    [sys.executable, "server.py", "--port", str(TEST_PORT)],
    env=dict(os.environ, FBARX_SIM="1")
)
time.sleep(2.5)

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1280,720')
opts.add_argument('--ignore-certificate-errors')
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
passed = []
failed = []

def record(name, condition, err=""):
    if condition:
        print(f"  [PASS] {name}")
        passed.append(name)
    else:
        print(f"  [FAIL] {name}: {err}")
        failed.append(f"{name}: {err}")

try:
    print(f"Connecting to {BASE_URL}...")
    driver.get(f"{BASE_URL}/")
    time.sleep(2.0)

    # ----------------------------------------------------
    # TEST 1: STN 1 Mode to MAN, open numpad, enter 45.5
    # ----------------------------------------------------
    print("\n--- 1. Testing STN 1 Output Numpad ---")
    stn1_man_btn = driver.find_element(By.CSS_SELECTOR, '#col-stn1 .mode-btn[data-mode="MAN"]')
    stn1_man_btn.click()
    time.sleep(0.5)

    # Click numpad symbol on STN 1 output
    stn1_pad_sym = driver.find_element(By.CSS_SELECTOR, '.output-numpad-symbol[data-output-pad="stn1"]')
    stn1_pad_sym.click()
    time.sleep(0.5)

    modal = driver.find_element(By.ID, 'numpad-modal')
    record("STN 1 Numpad Modal Opens", 'open' in modal.get_attribute('class'))

    title = driver.find_element(By.ID, 'numpad-target-title').text
    record("STN 1 Numpad Title Correct", "STN 1 OUTPUT" in title, f"Title was: {title}")

    # Type 45.5 using numpad keys
    for k in ["4", "5", ".", "5"]:
        btn_k = driver.find_element(By.CSS_SELECTOR, f'#numpad-grid .num-key[data-k="{k}"]')
        btn_k.click()
        time.sleep(0.1)

    disp_val = driver.find_element(By.ID, 'numpad-display-val').text
    record("Numpad displays typed 45.5", disp_val == "45.5", f"Display showed: {disp_val}")

    # Click Confirm & Set
    ok_btn = driver.find_element(By.ID, 'numpad-btn-ok')
    ok_btn.click()
    time.sleep(0.8)

    record("STN 1 Numpad Closes after Confirm", 'open' not in modal.get_attribute('class'))

    # Check DOM output text and bar width
    txt1 = driver.find_element(By.ID, 'stn1-out-bar-txt').text
    bar1 = driver.find_element(By.ID, 'stn1-out-bar').get_attribute('style')
    record("STN 1 bar text reflects 45.5%", "45.5%" in txt1 or "45.5" in txt1, f"Text was: {txt1}")
    record("STN 1 bar width reflects 45.5%", "45.5%" in bar1, f"Bar style was: {bar1}")

    # Verify server state persisted 45.5
    st = requests.get(f"{BASE_URL}/api/state").json()
    stn1_server_out = st["stn1"]["outputPct"]
    record("Server state reflects STN 1 output 45.5%", abs(stn1_server_out - 45.5) < 0.1, f"Server had: {stn1_server_out}")

    # ----------------------------------------------------
    # TEST 2: STN 2 MAN mode Decrement increases vs decreases
    # ----------------------------------------------------
    print("\n--- 2. Testing STN 2 Stepper Decrement & Increment ---")
    stn2_man_btn = driver.find_element(By.CSS_SELECTOR, '#col-stn2 .mode-btn[data-mode="MAN"]')
    stn2_man_btn.click()
    time.sleep(0.5)

    # Set STN 2 output to 50.0% so we have headroom to step down and step up
    requests.post(f"{BASE_URL}/api/action", json={"action": "set_output", "station": "stn2", "value": 50.0})
    time.sleep(0.6)

    # Initial state
    st_init = requests.get(f"{BASE_URL}/api/state").json()
    init_out2 = float(st_init["stn2"]["outputPct"])
    print(f"  Initial STN 2 output: {init_out2}%")
    record("STN 2 Output initially at 50%", abs(init_out2 - 50.0) < 0.1, f"Was: {init_out2}")

    # Click step down
    step_down = driver.find_element(By.ID, 'stn2-step-down')
    step_down.click()
    time.sleep(0.6)

    st_after_down = requests.get(f"{BASE_URL}/api/state").json()
    out2_after_down = float(st_after_down["stn2"]["outputPct"])
    print(f"  After step down: {out2_after_down}%")
    record("STN 2 Step Down DECREASES output", out2_after_down < init_out2, f"Initial: {init_out2}, After down: {out2_after_down}")
    record("STN 2 Step Down delta is exactly 1.0%", abs((init_out2 - out2_after_down) - 1.0) < 0.1, f"Delta was: {init_out2 - out2_after_down}")

    # Check UI text
    txt2 = driver.find_element(By.ID, 'stn2-out-bar-txt').text
    record("STN 2 bar text matches decreased output", f"{out2_after_down:.1f}%" in txt2 or f"{round(out2_after_down)}%" in txt2, f"Text was: {txt2}")

    # Click step up
    step_up = driver.find_element(By.ID, 'stn2-step-up')
    step_up.click()
    time.sleep(0.6)

    st_after_up = requests.get(f"{BASE_URL}/api/state").json()
    out2_after_up = float(st_after_up["stn2"]["outputPct"])
    print(f"  After step up: {out2_after_up}%")
    record("STN 2 Step Up INCREASES output", out2_after_up > out2_after_down, f"After down: {out2_after_down}, After up: {out2_after_up}")

    # ----------------------------------------------------
    # TEST 3: Numpad Dismissal on Mode Switch
    # ----------------------------------------------------
    print("\n--- 3. Testing Numpad Dismissal on Mode Switch ---")
    stn2_pad_sym = driver.find_element(By.CSS_SELECTOR, '.output-numpad-symbol[data-output-pad="stn2"]')
    stn2_pad_sym.click()
    time.sleep(0.5)
    record("Numpad opened for STN 2", 'open' in modal.get_attribute('class'))

    # Switch STN 2 to AUTO via action
    requests.post(f"{BASE_URL}/api/action", json={"action": "set_mode", "station": "stn2", "mode": "AUTO"})
    time.sleep(0.6)
    record("Numpad automatically closed when STN 2 switched to AUTO", 'open' not in modal.get_attribute('class'))

    # Put back to MAN and open again
    requests.post(f"{BASE_URL}/api/action", json={"action": "set_mode", "station": "stn2", "mode": "MAN"})
    time.sleep(0.6)
    stn2_pad_sym.click()
    time.sleep(0.5)
    record("Numpad reopened in MAN", 'open' in modal.get_attribute('class'))

    # Switch to OFF via action
    requests.post(f"{BASE_URL}/api/action", json={"action": "set_mode", "station": "stn2", "mode": "OFF"})
    time.sleep(0.6)
    record("Numpad automatically closed when STN 2 switched to OFF", 'open' not in modal.get_attribute('class'))

    # ----------------------------------------------------
    # TEST 4: Modal Z-index and Clean View Screenshot
    # ----------------------------------------------------
    print("\n--- 4. Checking Modal Z-index and Visual Rendering ---")
    requests.post(f"{BASE_URL}/api/action", json={"action": "set_mode", "station": "stn2", "mode": "MAN"})
    time.sleep(0.6)
    stn2_pad_sym.click()
    time.sleep(0.5)

    z_overlay = modal.value_of_css_property('z-index')
    record("Modal Overlay has high z-index (>= 2000000)", int(z_overlay) >= 2000000, f"z-index was: {z_overlay}")

    driver.save_screenshot("C:/Users/Admin/.gemini/antigravity/brain/c822483c-07f0-4930-a0f0-6eb6fb130cb4/numpad_clean_verified.png")
    print("  Clean numpad screenshot saved to artifacts.")
    
    ok_btn.click()
    time.sleep(0.5)

finally:
    driver.quit()
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except Exception:
        server_proc.kill()

print("\n" + "="*50)
print(f"RESULTS: {len(passed)} PASSED, {len(failed)} FAILED")
print("="*50)
if failed:
    sys.exit(1)
