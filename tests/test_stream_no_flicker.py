import subprocess
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

server_proc = subprocess.Popen(
    [sys.executable, "-u", "server.py", "--port", "11200"],
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
    print("Connecting to http://127.0.0.1:11200/...", flush=True)
    driver.get("http://127.0.0.1:11200/")
    time.sleep(3.0)

    # 1. Switch STN 2 to MAN mode
    print("\n--- 1. Testing Camera Stream Stability in MAN Mode ---", flush=True)
    stn2_man = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="MAN"]')
    stn2_man.click()
    time.sleep(1.0)

    live_cam_img = driver.find_element(By.ID, 'recipe-live-cam-img')
    record("Live camera img is visible in MAN mode", live_cam_img.is_displayed())
    src_initial_man = live_cam_img.get_attribute('src')
    record("Stream URL points to /api/camera/stream in MAN mode", "/api/camera/stream" in src_initial_man, f"src={src_initial_man}")

    # Set up a mutation count tracker on live_cam_img in the browser
    driver.execute_script("""
        window.__srcChangeCount = 0;
        const img = document.getElementById('recipe-live-cam-img');
        const observer = new MutationObserver(mutations => {
            mutations.forEach(m => {
                if (m.attributeName === 'src') window.__srcChangeCount++;
            });
        });
        observer.observe(img, { attributes: true });
    """)

    # Wait 4 seconds (16 polling cycles) to ensure zero reassignments happen
    print("  Monitoring stream URL stability over 4 seconds (16 poll cycles)...", flush=True)
    time.sleep(4.0)
    change_count_man = driver.execute_script("return window.__srcChangeCount;")
    current_src_man = live_cam_img.get_attribute('src')
    record("Stream URL was NOT repeatedly reassigned in MAN mode (zero flicker)", change_count_man == 0, f"Reassigned {change_count_man} times!")
    record("Stream URL remained identical", current_src_man == src_initial_man)

    # 2. Switch STN 2 to AUTO mode
    print("\n--- 2. Testing Camera Stream Stability in AUTO Mode ---", flush=True)
    stn2_auto = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="AUTO"]')
    stn2_auto.click()
    time.sleep(1.0)

    record("Live camera img is visible in AUTO mode", live_cam_img.is_displayed())
    src_initial_auto = live_cam_img.get_attribute('src')
    record("Stream URL points to /api/camera/stream in AUTO mode", "/api/camera/stream" in src_initial_auto)

    # Reset mutation count
    driver.execute_script("window.__srcChangeCount = 0;")
    print("  Monitoring stream URL stability over 4 seconds (16 poll cycles)...", flush=True)
    time.sleep(4.0)
    change_count_auto = driver.execute_script("return window.__srcChangeCount;")
    current_src_auto = live_cam_img.get_attribute('src')
    record("Stream URL was NOT repeatedly reassigned in AUTO mode (zero flicker)", change_count_auto == 0, f"Reassigned {change_count_auto} times!")
    record("Stream URL remained identical in AUTO mode", current_src_auto == src_initial_auto)

    # 3. Switch STN 2 to OFF mode
    print("\n--- 3. Testing Stream Teardown in OFF Mode ---", flush=True)
    stn2_off = driver.find_element(By.CSS_SELECTOR, '#col-stn2 [data-mode="OFF"]')
    stn2_off.click()
    time.sleep(1.0)
    off_overlay = driver.find_element(By.ID, 'live-cam-off-overlay')
    record("Off overlay displayed when STN 2 switches to OFF", off_overlay.is_displayed())
    record("Live camera img hidden when STN 2 switches to OFF", not live_cam_img.is_displayed())

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
