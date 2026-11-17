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
    
    res = driver.execute_script('''
        try {
            const screen = document.getElementById('report-screen');
            screen.classList.add('open');
            const rows = updateReportScreen();
            const body = document.getElementById('report-table-body');
            return {
                ok: true,
                rowsCount: rows ? rows.length : null,
                bodyHtml: body ? body.innerHTML : null,
                bodyChildren: body ? body.children.length : null
            };
        } catch(e) {
            return { ok: false, error: e.toString(), stack: e.stack };
        }
    ''')
    print('Direct call result:', res)
finally:
    driver.quit()
