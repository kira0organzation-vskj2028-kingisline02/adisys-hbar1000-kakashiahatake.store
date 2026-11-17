from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os, time

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--use-fake-ui-for-media-stream')
opts.add_argument('--use-fake-device-for-media-stream')
opts.add_argument('--window-size=1280,720')
driver = webdriver.Chrome(options=opts)

try:
    file_url = 'file:///' + os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(file_url)
    time.sleep(1)

    # 1. Open Recipe Load Screen
    driver.execute_script("if(typeof showRecipeLoadScreen === 'function') showRecipeLoadScreen();")
    time.sleep(1)

    s = driver.find_element(By.ID, 'recipe-load-screen')
    assert 'open' in s.get_attribute('class'), "Recipe load screen should be open"
    print("Recipe load screen opened successfully.")

    # 2. Click OPEN CAMERA
    btn = driver.find_element(By.ID, 'recipe-camera-open')
    print("Clicking OPEN CAMERA...")
    driver.execute_script("arguments[0].click();", btn)
    time.sleep(1.5)

    print("Btn text after open:", btn.text)
    assert "CLOSE CAMERA" in btn.text, f"Expected CLOSE CAMERA, got {btn.text}"

    status_el = driver.find_element(By.ID, 'recipe-camera-status')
    print("Camera status:", status_el.text)
    assert "LIVE" in status_el.text, f"Expected LIVE in status, got {status_el.text}"

    # 3. Check auto-detect timer is active
    timer_active = driver.execute_script("return autoDetectTimer !== null;")
    print("Auto-detect timer active:", timer_active)
    assert timer_active, "autoDetectTimer should be running"

    # 4. Check video or stream element is visible
    vid = driver.find_element(By.ID, 'recipe-camera-video')
    img = driver.find_element(By.ID, 'recipe-camera-stream-img')
    vid_disp = vid.value_of_css_property('display')
    img_disp = img.value_of_css_property('display')
    print(f"Video display: {vid_disp}, Stream Img display: {img_disp}")
    assert vid_disp != 'none' or img_disp != 'none', "Either video or stream img should be visible"

    # 5. Take screenshot of recipe screen with active camera
    driver.find_element(By.ID, 'recipe-load-screen').screenshot('recipe_camera_active.png')
    print("Screenshot saved to recipe_camera_active.png")

    # 6. Click READ & COMPARE
    btn_compare = driver.find_element(By.ID, 'recipe-camera-compare')
    assert 'btn-cam-disabled' not in btn_compare.get_attribute('class'), "Compare button should be enabled"
    driver.execute_script("arguments[0].click();", btn_compare)
    time.sleep(1)

    sift_status = driver.find_element(By.ID, 'recipe-sift-status').text
    compare_res = driver.find_element(By.ID, 'recipe-compare-result').text
    print(f"SIFT Status: {sift_status}")
    print(f"Compare Result: {compare_res}")

    # 7. Close camera
    driver.execute_script("arguments[0].click();", btn)
    time.sleep(0.5)
    print("Btn text after close:", btn.text)
    assert "OPEN CAMERA" in btn.text, f"Expected OPEN CAMERA after close, got {btn.text}"
    print("Camera status after close:", status_el.text)
    assert "OFF" in status_el.text, f"Expected OFF in status, got {status_el.text}"

    print("ALL RECIPE CAMERA TESTS PASSED!")
finally:
    driver.quit()
