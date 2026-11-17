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
    
    dims = driver.execute_script('''
        const scr = document.getElementById("stn1-cal-screen");
        if (scr) scr.classList.add("open");
        document.getElementById("stn1-password-screen").style.display = "none";
        document.getElementById("stn1-control-screen").style.display = "none";
        const lScreen = document.getElementById("stn1-loadcell-screen");
        lScreen.style.display = "flex";
        
        const zeroRow = document.querySelector("#stn1-loadcell-screen .cal-zero-row");
        const zeroBtn = document.getElementById("cal-zero");
        const calInfo = document.querySelector("#stn1-loadcell-screen .cal-zero-row .cal-info");
        const fieldInfo = document.querySelector("#stn1-loadcell-screen .field-instrument-info");
        
        return {
            zeroRow: zeroRow ? { w: zeroRow.offsetWidth, h: zeroRow.offsetHeight } : null,
            zeroBtn: zeroBtn ? { w: zeroBtn.offsetWidth, h: zeroBtn.offsetHeight } : null,
            calInfo: calInfo ? { w: calInfo.offsetWidth, h: calInfo.offsetHeight } : null,
            fieldInfo: fieldInfo ? { w: fieldInfo.offsetWidth, h: fieldInfo.offsetHeight } : null,
        };
    ''')
    print('Dimensions:', dims)
finally:
    driver.quit()
