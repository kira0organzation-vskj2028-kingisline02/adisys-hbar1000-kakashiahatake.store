import os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--window-size=800,480')
opts.add_argument('--hide-scrollbars')

driver = webdriver.Chrome(options=opts)
try:
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width': 800,
        'height': 480,
        'deviceScaleFactor': 1,
        'mobile': False
    })
    file_path = os.path.abspath('static/index.html')
    driver.get(f'file:///{file_path.replace(os.sep, "/")}')
    time.sleep(0.5)
    
    driver.execute_script("""
        const scr = document.getElementById('stn1-cal-screen');
        if (scr) scr.classList.add('open');
        const pScreen = document.getElementById('stn1-password-screen');
        if (pScreen) pScreen.style.display = 'none';
        const cScreen = document.getElementById('stn1-control-screen');
        if (cScreen) cScreen.style.display = 'none';
        const lScreen = document.getElementById('stn1-loadcell-screen');
        if (lScreen) lScreen.style.display = 'flex';
        if (typeof updateCalibrationDisplay === 'function') updateCalibrationDisplay();
    """)
    time.sleep(0.5)
    
    out_dir = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    out_png = os.path.join(out_dir, 'loadcell_800x480.png')
    driver.save_screenshot(out_png)
    
    from PIL import Image
    im = Image.open(out_png)
    print(f'Exact viewport image size: {im.size}')
finally:
    driver.quit()
