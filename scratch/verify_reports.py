import subprocess, time, sys, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TEST_PORT = 11288
server_proc = subprocess.Popen(
    [sys.executable, "server.py", "--port", str(TEST_PORT)],
    env=dict(os.environ, FBARX_SIM="1")
)
time.sleep(2)

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--window-size=800,480')
opts.add_argument('--hide-scrollbars')
driver = webdriver.Chrome(options=opts)

try:
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width': 800, 'height': 480, 'deviceScaleFactor': 1, 'mobile': False
    })
    driver.get(f'http://127.0.0.1:{TEST_PORT}/')
    time.sleep(1.5)
    
    # Open report screen
    btn_rep = driver.find_element('id', 'btn-open-report')
    btn_rep.click()
    time.sleep(1.5)
    
    res = driver.execute_script('''
        const screen = document.getElementById('report-screen');
        const isOpen = screen ? screen.classList.contains('open') : false;
        const body = document.getElementById('report-table-body');
        const rows = body ? body.querySelectorAll('tr') : [];
        const recordsCount = window.HMI_STATE?.report?.records?.length || 0;
        const totalBags = document.getElementById('report-count-total')?.textContent;
        const statusText = document.getElementById('report-status')?.textContent;
        
        return {
            screenOpen: isOpen,
            recordsCount: recordsCount,
            tableRowsCount: rows.length,
            firstRowText: rows.length > 0 ? rows[0].innerText : '',
            totalBags: totalBags,
            statusText: statusText
        };
    ''')
    print('Report verification result:', res)
    
    dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    driver.save_screenshot(f'{dir_p}\\verified_report_screen.png')
    print('Saved verified_report_screen.png')
    
    assert res['screenOpen'] == True
    assert res['recordsCount'] > 0, "Database records were not loaded!"
    assert res['tableRowsCount'] > 0, "Table rows were not rendered!"
    print("PASS: Reports are now loading and displaying beautifully!")
finally:
    driver.quit()
    server_proc.terminate()
    server_proc.wait(timeout=2)
