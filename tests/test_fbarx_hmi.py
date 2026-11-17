import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_test():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=800,480")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(800, 480)

    try:
        print("Navigating to http://127.0.0.1:8000 ...")
        driver.get("http://127.0.0.1:8000")
        time.sleep(2)

        # 1. Check serial text in status bar
        status_bar = driver.find_element(By.CSS_SELECTOR, "footer.bottombar").get_attribute("textContent")
        print(f"Status bar textContent: '{status_bar}'")
        assert "9600-8O1" in status_bar, f"Expected 9600-8O1 in status bar, got {status_bar}"

        # 2. Check REPEAT LENGTH SET label on Screen 1
        tile_repeat_hdr = driver.find_element(By.CSS_SELECTOR, "#tile-repeat-length .metric-tile-hdr label").text
        print(f"Repeat length tile label: '{tile_repeat_hdr}'")
        assert tile_repeat_hdr == "REPEAT LENGTH SET", f"Expected 'REPEAT LENGTH SET', got '{tile_repeat_hdr}'"

        # 3. Check STN 2 ammeter card title
        ammeter_title = driver.find_element(By.ID, "stn2-ammeter-card").get_attribute("title")
        print(f"STN 2 ammeter card title: '{ammeter_title}'")
        assert "BRAKE CURRENT ACTUAL" in ammeter_title, f"Expected 'BRAKE CURRENT ACTUAL' in title, got '{ammeter_title}'"

        # 4. Check initial REP display format
        rep_text = driver.find_element(By.ID, "mark-error-readout").text
        print(f"REP readout in initial state: '{rep_text}'")
        # In OFF mode, should be REP: --- mm
        assert "REP:" in rep_text, f"Expected 'REP:' in text, got '{rep_text}'"

        # Take screenshot of Screen 1
        out_dir = r"C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4"
        screen1_off_path = os.path.join(out_dir, "screen1_stn2_off_fbarx.png")
        driver.save_screenshot(screen1_off_path)
        print(f"Saved screenshot: {screen1_off_path}")

        # 5. Switch STN 2 to AUTO mode
        print("Clicking AUTO button on STN 2...")
        btn_auto = driver.find_element(By.CSS_SELECTOR, "#col-stn2 .mode-btn[data-mode='AUTO']")
        btn_auto.click()
        time.sleep(2.5)  # Wait for simulation cycle

        rep_auto_text = driver.find_element(By.ID, "mark-error-readout").text
        print(f"REP readout in AUTO state: '{rep_auto_text}'")
        assert "REP:" in rep_auto_text and "mm" in rep_auto_text, f"Unexpected REP format: '{rep_auto_text}'"

        # Check detection chips
        chips = driver.find_elements(By.CSS_SELECTOR, "#col-stn2 .detection-grid .zone-chip")
        chip_labels = [c.find_element(By.TAG_NAME, "small").text for c in chips]
        print(f"Detection chips rendered ({len(chips)}): {chip_labels}")
        assert len(chips) >= 3, f"Expected at least 3 chips, got {len(chips)}"
        assert chip_labels[-1] == "TOTAL", f"Expected last chip to be TOTAL, got '{chip_labels[-1]}'"

        screen1_auto_path = os.path.join(out_dir, "screen1_stn2_auto_fbarx.png")
        driver.save_screenshot(screen1_auto_path)
        print(f"Saved screenshot: {screen1_auto_path}")

        # 6. Switch STN 2 to MAN mode
        print("Clicking MAN button on STN 2...")
        btn_man = driver.find_element(By.CSS_SELECTOR, "#col-stn2 .mode-btn[data-mode='MAN']")
        btn_man.click()
        time.sleep(1.5)

        screen1_man_path = os.path.join(out_dir, "screen1_stn2_man_fbarx.png")
        driver.save_screenshot(screen1_man_path)
        print(f"Saved screenshot: {screen1_man_path}")

        # 7. Test STN 2 Calibration modal opening and fields
        print("Clicking STN 2 CAL button...")
        btn_cal = driver.find_element(By.ID, "btn-stn2-cal")
        driver.execute_script("arguments[0].click();", btn_cal)
        WebDriverWait(driver, 5).until(lambda d: "open" in d.find_element(By.ID, "numpad-modal").get_attribute("class"))
        time.sleep(0.3)

        # Enter password 3333 on numpad modal
        print("Entering password 3333...")
        key_3 = driver.find_element(By.CSS_SELECTOR, "#numpad-modal .num-key[data-k='3']")
        for _ in range(4):
            driver.execute_script("arguments[0].click();", key_3)
            time.sleep(0.1)

        btn_confirm = driver.find_element(By.ID, "numpad-btn-ok")
        driver.execute_script("arguments[0].click();", btn_confirm)
        WebDriverWait(driver, 5).until(lambda d: "open" in d.find_element(By.ID, "stn2-cal-screen").get_attribute("class"))
        time.sleep(0.5)

        # Check STN 2 Calibration screen
        cal_screen = driver.find_element(By.ID, "stn2-cal-screen")
        assert "open" in cal_screen.get_attribute("class"), "STN 2 calibration screen failed to open"
        print("STN 2 calibration screen is OPEN.")

        # Check rows (16 parameters + 1 available brake capacity = 17 rows)
        rows = cal_screen.find_elements(By.CSS_SELECTOR, ".cal-grid .cal-row")
        print(f"Found {len(rows)} calibration rows in screen:")
        for r in rows:
            print("  - " + r.text.replace("\n", " | "))

        assert len(rows) >= 16, f"Expected at least 16 calibration rows, found {len(rows)}"

        # Verify available brake capacity row
        avail_cap_row = cal_screen.find_element(By.ID, "stn2-cal-avail-capacity-row")
        assert "AVAILABLE BRAKE CAPACITY" in avail_cap_row.text
        assert "kgm" in avail_cap_row.text

        # Verify board lock status badge
        lock_badge = cal_screen.find_element(By.ID, "stn2-board-lock-badge")
        assert lock_badge is not None

        # Verify field names and defaults
        brake_power_row = cal_screen.find_element(By.CSS_SELECTOR, "[data-stn2-cal-target='brakePower']")
        assert "BRAKE POWER SET" in brake_power_row.text
        assert "%" in brake_power_row.text

        brake_cap_row = cal_screen.find_element(By.CSS_SELECTOR, "[data-stn2-cal-target='brakeCapacity']")
        assert "kgm" in brake_cap_row.text

        brake_cur_row = cal_screen.find_element(By.CSS_SELECTOR, "[data-stn2-cal-target='brakeCurrent']")
        assert "A" in brake_cur_row.text

        brake_cal_row = cal_screen.find_element(By.CSS_SELECTOR, "[data-stn2-cal-target='brakeCurrentCal']")
        assert "mA" in brake_cal_row.text

        set_tension_row = cal_screen.find_element(By.ID, "stn2-cal-setTension")
        assert set_tension_row is not None

        cal_modal_path = os.path.join(out_dir, "stn2_calibration_modal_fbarx.png")
        driver.save_screenshot(cal_modal_path)
        print(f"Saved screenshot: {cal_modal_path}")

        # Close calibration screen via HOME button
        btn_home_cal = driver.find_element(By.ID, "stn2-cal-home")
        btn_home_cal.click()
        time.sleep(0.5)

        print("\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

    finally:
        driver.quit()

if __name__ == "__main__":
    run_test()
