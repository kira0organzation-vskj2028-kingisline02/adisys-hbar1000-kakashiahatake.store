from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os, time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--window-size=800,480')
opts.add_argument('--hide-scrollbars')

driver = webdriver.Chrome(options=opts)
try:
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width': 800, 'height': 480, 'deviceScaleFactor': 1, 'mobile': False
    })
    file_path = os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(f'file:///{file_path}')
    time.sleep(0.5)
    
    # Click REPORT button
    rep_btn = driver.find_element('id', 'btn-open-report')
    rep_btn.click()
    time.sleep(0.5)
    
    # Check report table
    tbody = driver.find_element('id', 'report-table-body')
    print('Report tbody text:', repr(tbody.text))
    
    dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    driver.save_screenshot(f'{dir_p}\\report_screen_test.png')
    print('Saved report_screen_test.png')
finally:
    driver.quit()
