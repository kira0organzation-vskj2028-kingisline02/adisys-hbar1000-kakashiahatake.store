from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import sys
import time

def run_tests():
    target_url = 'https://adisys.kakashihatake.store/'
    if len(sys.argv) > 1 and sys.argv[1].startswith('http'):
        target_url = sys.argv[1]

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1024,600')
    options.add_argument('--ignore-certificate-errors')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    driver = webdriver.Chrome(options=options)

    print(f"Connecting to: {target_url}")
    driver.get(target_url)
    time.sleep(3)

    # Save visual screenshot of live site
    driver.save_screenshot('C:/Users/Admin/.gemini/antigravity/brain/c822483c-07f0-4930-a0f0-6eb6fb130cb4/live_adisys_site.png')
    print("Saved initial screenshot to live_adisys_site.png")

    print("--- 1. Testing RECIPE button (#btn-load-slaves) ---")
    btn_recipe = driver.find_element('id', 'btn-load-slaves')
    btn_recipe.click()
    time.sleep(1)
    recipe_screen_classes = driver.find_element('id', 'recipe-load-screen').get_attribute('class')
    print(f"Recipe screen classes: {recipe_screen_classes}")
    assert 'open' in recipe_screen_classes, "Recipe load screen must open on click!"

    # Test OFF alert when stations are OFF
    driver.execute_script("""
        document.querySelectorAll('#col-stn1 .mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'OFF'));
        document.querySelectorAll('#col-stn2 .mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'OFF'));
        window.HMI_STATE.stn1.mode = 'OFF';
        window.HMI_STATE.stn2.mode = 'OFF';
    """)
    btn_save = driver.find_element('id', 'recipe-load-save')
    btn_save.click()
    time.sleep(0.5)
    toast = driver.find_element('id', 'toast')
    print(f"Recipe OFF toast text: {toast.text}")
    assert 'STATIONS IN OFF MODE' in toast.text

    # Restore STN 1 to MAN
    driver.execute_script("""
        document.querySelectorAll('#col-stn1 .mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'MAN'));
        window.HMI_STATE.stn1.mode = 'MAN';
    """)

    # Close recipe load screen by clicking home
    driver.find_element('id', 'recipe-load-home').click()
    time.sleep(0.5)
    print("Recipe screen closed successfully.")

    print("\n--- 2. Testing REPORT button (#btn-open-report) ---")
    btn_report = driver.find_element('id', 'btn-open-report')
    btn_report.click()
    time.sleep(1)
    report_screen_classes = driver.find_element('id', 'report-screen').get_attribute('class')
    print(f"Report screen classes: {report_screen_classes}")
    assert 'open' in report_screen_classes, "Report screen must open on click!"

    # Close report screen by clicking home
    driver.find_element('id', 'report-home').click()
    time.sleep(0.5)
    print("Report screen closed successfully.")

    print("\n--- 3. Testing CALIBRATE button on home screen (#btn-quick-new) ---")
    btn_cal = driver.find_element('id', 'btn-quick-new')
    btn_cal.click()
    time.sleep(1)
    pad_modal = driver.find_element('id', 'numpad-modal').get_attribute('class')
    print(f"Numpad modal class: {pad_modal}")
    assert 'open' in pad_modal, "Numpad modal must open on CALIBRATE click!"

    # Click key 4 four times for passcode 4444
    for _ in range(4):
        driver.find_element('css selector', '.num-key[data-k="4"]').click()
    time.sleep(0.2)
    driver.find_element('id', 'numpad-btn-ok').click()
    time.sleep(1)
    cal_screen_classes = driver.find_element('id', 'screen-recipe').get_attribute('class')
    print(f"Calibrate screen classes after entering 4444: {cal_screen_classes}")
    assert 'active' in cal_screen_classes, "Calibrate screen must be active!"

    # Click home/discard on calibrate screen
    driver.find_element('id', 'btn-discard-recipe').click()
    time.sleep(0.5)
    print("Calibrate screen closed successfully.")

    print("\n--- 4. Testing LIVE CAM plate with STN 2 in MAN mode ---")
    # Switch STN 2 to MAN
    driver.execute_script("document.querySelector('#col-stn2 .mode-btn[data-mode=\"MAN\"]').click();")
    time.sleep(0.5)
    stn2_mode = driver.execute_script("return window.HMI_STATE.stn2.mode;")
    print(f"STN 2 mode: {stn2_mode}")
    assert stn2_mode == 'MAN'

    # Click live cam plate
    driver.find_element('id', 'recipe-live-cam-plate').click()
    time.sleep(1)
    cam_screen_classes = driver.find_element('id', 'screen-cam').get_attribute('class')
    print(f"Screen-cam classes: {cam_screen_classes}")
    assert 'active' in cam_screen_classes, "Screen cam must be active when clicked in MAN mode!"

    # Return to main HMI
    btn_cam_home = driver.find_element('id', 'btn-cam-return-home')
    driver.execute_script("arguments[0].click();", btn_cam_home)
    time.sleep(0.5)
    home_classes = driver.find_element('id', 'screen-stn').get_attribute('class')
    print(f"Home screen classes after return: {home_classes}")
    assert 'active' in home_classes, "Home screen must be active!"

    print("\n--- 5. Testing LIVE CAM plate with STN 2 in OFF mode (Standby live inspection) ---")
    # Switch STN 2 to OFF
    driver.execute_script("document.querySelector('#col-stn2 .mode-btn[data-mode=\"OFF\"]').click();")
    time.sleep(0.5)
    driver.find_element('id', 'recipe-live-cam-plate').click()
    time.sleep(0.8)
    cam_screen_classes_off = driver.find_element('id', 'screen-cam').get_attribute('class')
    badge_off = driver.find_element('id', 'full-cam-mode-badge').text
    print(f"Screen-cam classes when STN 2 is OFF: {cam_screen_classes_off}, badge: {badge_off}")
    assert 'active' in cam_screen_classes_off, "Screen cam must open when clicked in OFF mode!"
    assert 'STANDBY' in badge_off, f"Badge must indicate STANDBY, got: {badge_off}"

    # Return to main HMI
    driver.execute_script("arguments[0].click();", driver.find_element('id', 'btn-cam-return-home'))
    time.sleep(0.5)
    home_classes = driver.find_element('id', 'screen-stn').get_attribute('class')
    assert 'active' in home_classes, "Home screen must be active after returning from OFF mode cam!"

    print("\n--- 5b. Testing LIVE CAM plate with STN 2 in AUTO mode ---")
    driver.execute_script("document.querySelector('#col-stn2 .mode-btn[data-mode=\"AUTO\"]').click();")
    time.sleep(0.5)
    driver.find_element('id', 'recipe-live-cam-plate').click()
    time.sleep(0.8)
    cam_screen_classes_auto = driver.find_element('id', 'screen-cam').get_attribute('class')
    badge_auto = driver.find_element('id', 'full-cam-mode-badge').text
    print(f"Screen-cam classes when STN 2 is AUTO: {cam_screen_classes_auto}, badge: {badge_auto}")
    assert 'active' in cam_screen_classes_auto, "Screen cam must open when clicked in AUTO mode!"
    assert 'AUTO' in badge_auto, f"Badge must indicate AUTO, got: {badge_auto}"

    # Return to main HMI
    driver.execute_script("arguments[0].click();", driver.find_element('id', 'btn-cam-return-home'))
    time.sleep(0.5)
    home_classes = driver.find_element('id', 'screen-stn').get_attribute('class')
    assert 'active' in home_classes, "Home screen must be active after returning from AUTO mode cam!"

    print("\n--- 6. Checking browser console logs ---")
    logs = driver.get_log('browser')
    severe_logs = [l for l in logs if l['level'] == 'SEVERE' and 'favicon' not in l['message']]
    print(f"Severe errors: {severe_logs}")
    assert len(severe_logs) == 0, "No severe console errors allowed!"

    print("\n>>> ALL FUNCTIONAL TESTS PASSED 100%! <<<")
    driver.quit()

if __name__ == '__main__':
    run_tests()
