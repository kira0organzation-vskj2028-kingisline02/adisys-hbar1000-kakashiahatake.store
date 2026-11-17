from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os, time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--window-size=800,480')
driver = webdriver.Chrome(options=opts)

try:
    file_path = os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(f'file:///{file_path}')
    time.sleep(0.5)

    # 1. Unlock STN 2 Calibration
    res = driver.execute_script('''
        const scr2 = document.getElementById('stn2-cal-screen');
        scr2.classList.add('open');
        
        // Open numpad for ACerr
        openStn2CalibrationPad('acErr');
        const modal = document.getElementById('numpad-modal');
        const isModalOpen = modal.classList.contains('open');
        
        // Click CAN (cancel button)
        const canBtn = document.getElementById('numpad-btn-cancel');
        canBtn.click();
        
        const isModalOpenAfter = modal.classList.contains('open');
        const isStn2StillOpen = scr2.classList.contains('open');
        
        return {
            modalOpened: isModalOpen,
            modalClosedAfterCan: !isModalOpenAfter,
            stn2RemainsOpen: isStn2StillOpen
        };
    ''')
    print('STN 2 Numpad CAN test result:', res)
    assert res['modalOpened'] == True
    assert res['modalClosedAfterCan'] == True
    assert res['stn2RemainsOpen'] == True
    print('PASS: STN 2 Calibration stays open when numpad CAN is pressed!')
finally:
    driver.quit()
