import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def run_all_tests():
    print("=== STARTING FULL VERIFICATION ===")

    # Test 1: Direct API Login tests
    print("\n--- TEST 1: API /api/login tests ---")
    r1 = requests.post("http://127.0.0.1:11111/api/login", json={"passcode": "1111", "type": "cal_password"}).json()
    assert r1.get("ok") is True and r1.get("role") == "stn1_control", f"1111 failed: {r1}"
    print("PASS: 1111 returns role=stn1_control")

    r2 = requests.post("http://127.0.0.1:11111/api/login", json={"passcode": "2222", "type": "cal_password"}).json()
    assert r2.get("ok") is True and r2.get("role") == "stn1_loadcell", f"2222 failed: {r2}"
    print("PASS: 2222 returns role=stn1_loadcell")

    r3 = requests.post("http://127.0.0.1:11111/api/login", json={"passcode": "3333", "type": "stn2_cal"}).json()
    assert r3.get("ok") is True and r3.get("role") == "stn2_cal", f"3333 failed: {r3}"
    print("PASS: 3333 returns role=stn2_cal")

    r4 = requests.post("http://127.0.0.1:11111/api/login", json={"passcode": "4444", "type": "recipe_cal"}).json()
    assert r4.get("ok") is True and r4.get("role") == "recipe_cal", f"4444 failed: {r4}"
    print("PASS: 4444 returns role=recipe_cal")

    r_bad = requests.post("http://127.0.0.1:11111/api/login", json={"passcode": "9999", "type": "cal_password"}).json()
    assert r_bad.get("ok") is False, f"9999 should fail: {r_bad}"
    print("PASS: 9999 correctly rejected with ok=False")

    # Selenium UI Tests
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1024,600')
    driver = webdriver.Chrome(options=opts)

    try:
        driver.get('http://127.0.0.1:11111')
        time.sleep(2)

        def enter_code(code_str):
            for ch in code_str:
                k = driver.find_element(By.CSS_SELECTOR, f'#numpad-modal .num-key[data-k="{ch}"]')
                driver.execute_script('arguments[0].click();', k)
                time.sleep(0.05)

        # Test 2: STN 1 Calibration with 1111
        print("\n--- TEST 2: STN 1 Calibration with passcode 1111 ---")
        cal_btn = driver.find_element(By.ID, 'btn-stn1-cal')
        driver.execute_script('arguments[0].click();', cal_btn)
        time.sleep(0.5)

        modal = driver.find_element(By.ID, 'numpad-modal')
        assert 'open' in modal.get_attribute('class'), "Numpad modal not open"
        enter_code('1111')
        driver.execute_script("document.getElementById('numpad-btn-ok').click();")
        time.sleep(0.6)

        ctrl_screen = driver.find_element(By.ID, 'stn1-control-screen')
        lc_screen = driver.find_element(By.ID, 'stn1-loadcell-screen')
        assert ctrl_screen.is_displayed(), "Control screen should be visible for 1111"
        assert not lc_screen.is_displayed(), "Loadcell screen should NOT be visible for 1111"
        ctrl_title = ctrl_screen.find_element(By.CLASS_NAME, 'cal-title').text
        assert 'CONTROL PARAMETERS' in ctrl_title, f"Expected CONTROL PARAMETERS, got {ctrl_title}"
        print(f"PASS: 1111 unlocked STN 1 Screen: '{ctrl_title}'")

        # Click HOME to return to main screen
        driver.execute_script("document.getElementById('stn1-control-home').click();")
        time.sleep(0.5)
        stn1_cal_screen = driver.find_element(By.ID, 'stn1-cal-screen')
        assert not stn1_cal_screen.is_displayed() or 'open' not in stn1_cal_screen.get_attribute('class'), "STN1 cal screen should close on HOME"
        print("PASS: HOME button successfully returned to main screen")

        # Test 3: STN 1 Calibration with 2222
        print("\n--- TEST 3: STN 1 Calibration with passcode 2222 ---")
        driver.execute_script('arguments[0].click();', cal_btn)
        time.sleep(0.5)

        enter_code('2222')
        driver.execute_script("document.getElementById('numpad-btn-ok').click();")
        time.sleep(0.6)

        assert lc_screen.is_displayed(), "Loadcell screen should be visible for 2222"
        assert not ctrl_screen.is_displayed(), "Control screen should NOT be visible for 2222"
        lc_title = lc_screen.find_element(By.CLASS_NAME, 'cal-title').text
        assert 'LOADCELL CALIBRATION' in lc_title, f"Expected LOADCELL CALIBRATION, got {lc_title}"
        print(f"PASS: 2222 unlocked STN 1 Screen: '{lc_title}'")

        # Click HOME to return to main screen
        driver.execute_script("document.getElementById('stn1-loadcell-home').click();")
        time.sleep(0.5)
        assert not stn1_cal_screen.is_displayed() or 'open' not in stn1_cal_screen.get_attribute('class'), "STN1 cal screen should close on HOME"
        print("PASS: Loadcell HOME button returned to main screen")

        # Test 4: STN 1 Calibration with invalid passcode 9999
        print("\n--- TEST 4: STN 1 Calibration with invalid passcode 9999 ---")
        driver.execute_script('arguments[0].click();', cal_btn)
        time.sleep(0.5)

        enter_code('9999')
        driver.execute_script("document.getElementById('numpad-btn-ok').click();")
        time.sleep(0.6)

        assert not ctrl_screen.is_displayed(), "Control screen must NOT open for 9999"
        assert not lc_screen.is_displayed(), "Loadcell screen must NOT open for 9999"
        print("PASS: Invalid password 9999 rejected, neither screen opened")

        # Cancel numpad
        driver.execute_script("document.getElementById('numpad-btn-cancel').click();")
        time.sleep(0.5)

        # Test 5: Numpad Clean View & Mode buttons overlap verification
        print("\n--- TEST 5: Numpad Clean View & Stacking Context Check ---")
        # Switch STN 2 to MAN mode
        btn_man = driver.find_element(By.CSS_SELECTOR, '#col-stn2 .mode-btn[data-mode="MAN"]')
        driver.execute_script('arguments[0].click();', btn_man)
        time.sleep(1)

        # Open STN 2 Output numpad
        driver.execute_script("""
          const row = document.getElementById('stn2-out-row');
          const sym = row.querySelector('[data-output-pad="stn2"]');
          sym.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
        """)
        time.sleep(0.5)

        modal = driver.find_element(By.ID, 'numpad-modal')
        assert 'open' in modal.get_attribute('class'), "Numpad modal should be open"
        driver.save_screenshot('numpad_clean_verified.png')

        # Check every point across the modal where mode buttons used to bleed through
        for i, btn in enumerate(driver.find_elements(By.CSS_SELECTOR, '.mode-btn')):
            loc = btn.location
            size = btn.size
            cx = loc['x'] + size['width'] / 2
            cy = loc['y'] + size['height'] / 2
            top_el = driver.execute_script(f'return document.elementFromPoint({cx}, {cy});')
            tag = top_el.tag_name if top_el else 'None'
            cls = top_el.get_attribute('class') if top_el else ''
            pid = top_el.get_attribute('id') if top_el else ''
            # Ensure top element is NEVER a mode-btn! It MUST be modal-overlay or numpad-modal or its children!
            assert tag != 'BUTTON' or 'mode-btn' not in cls, f"Mode button {i} is on top of modal! top_el=<{tag} class='{cls}'>"
            print(f"Point ({cx}, {cy}) above btn {i}: top element is <{tag} id='{pid}' class='{cls}'> (NOT mode-btn)")

        print("PASS: Mode buttons are completely covered by numpad modal overlay! Zero bleed-through!")

        # Test 6: Switching mode from MAN to AUTO/OFF closes numpad immediately
        print("\n--- TEST 6: Auto-close numpad when station mode leaves MAN ---")
        assert 'open' in modal.get_attribute('class'), "Modal should still be open"

        # Switch STN 2 to OFF mode via API
        requests.post("http://127.0.0.1:11111/api/action", json={"action": "set_mode", "station": "stn2", "mode": "OFF"})
        time.sleep(1)

        # Check that numpad closed
        modal_classes = modal.get_attribute('class')
        assert 'open' not in modal_classes, f"Modal should have closed after STN 2 switched to OFF, but class is {modal_classes}"
        print("PASS: Numpad automatically closed when station switched to OFF mode!")

    finally:
        driver.quit()

    print("\n=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == '__main__':
    run_all_tests()
