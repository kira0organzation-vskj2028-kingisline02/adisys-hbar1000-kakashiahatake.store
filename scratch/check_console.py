from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os, time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--window-size=800,480')
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
try:
    file_path = os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(f'file:///{file_path}')
    time.sleep(0.5)
    
    driver.find_element('id', 'btn-open-report').click()
    time.sleep(0.5)
    
    logs = driver.get_log('browser')
    for log in logs:
        print(log)
        
    res = driver.execute_script('''
        return {
            hmiReport: window.HMI_STATE?.report,
            records: reportGetRecords(),
            filtered: reportFilteredRecords(),
            tbodyHtml: document.getElementById('report-table-body')?.innerHTML
        };
    ''')
    print('JS Exec Result:', res)
finally:
    driver.quit()
