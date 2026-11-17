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

    # Open recipe load screen
    driver.execute_script("if(typeof showRecipeLoadScreen === 'function') showRecipeLoadScreen();")
    time.sleep(1)

    s = driver.find_element(By.ID, 'recipe-load-screen')
    print('recipe-load-screen class:', s.get_attribute('class'))

    # Find OPEN CAMERA button
    btn = driver.find_element(By.ID, 'recipe-camera-open')
    print('OPEN CAMERA btn text before click:', btn.text)

    # Click it!
    btn.click()
    time.sleep(1)

    print('OPEN CAMERA btn text after click:', btn.text)
    st = driver.find_element(By.ID, 'recipe-camera-status').text
    print('recipe-camera-status:', st)

    vid = driver.find_element(By.ID, 'recipe-camera-video')
    has_src = driver.execute_script('return !!arguments[0].srcObject;', vid)
    print('video display:', vid.value_of_css_property('display'), 'srcObject exists:', has_src)

    img = driver.find_element(By.ID, 'recipe-camera-stream-img')
    print('stream-img display:', img.value_of_css_property('display'), 'src:', img.get_attribute('src'))

    logs = driver.get_log('browser')
    for l in logs:
        if l['level'] in ('SEVERE', 'WARNING'):
            print('BROWSER LOG:', l)
finally:
    driver.quit()
