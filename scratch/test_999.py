from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
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
    time.sleep(0.3)
    
    driver.execute_script("""
        const scr = document.getElementById("stn1-cal-screen");
        if (scr) scr.classList.add("open");
        document.getElementById("stn1-password-screen").style.display = "none";
        document.getElementById("stn1-control-screen").style.display = "none";
        document.getElementById("stn1-loadcell-screen").style.display = "flex";
        
        const calInfo = document.querySelector("#stn1-loadcell-screen .cal-zero-row .cal-info");
        calInfo.innerHTML = `
            <div class="cal-live-item">
                <span class="cal-live-label">WEIGHT</span>
                <b class="cal-live-val" id="cal-knownWeight">999 kg</b>
            </div>
            <div class="cal-live-item">
                <span class="cal-live-label">SIGNAL</span>
                <b class="cal-live-val" id="cal-signal-val">±4.0 mV</b>
            </div>
        `;
        calInfo.style.cssText = `
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 10px !important;
            padding: 8px 14px !important;
            align-items: center !important;
            box-sizing: border-box !important;
            background: var(--panel) !important;
            border: 1px solid var(--border) !important;
            border-radius: 7px !important;
        `;
        const style = document.createElement('style');
        style.innerHTML = `
            #stn1-loadcell-screen .cal-live-item {
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
                gap: 2px !important;
                min-width: 0 !important;
            }
            #stn1-loadcell-screen .cal-live-label {
                font-family: var(--font-mono) !important;
                font-size: 11px !important;
                font-weight: 700 !important;
                color: var(--tx-dim) !important;
                letter-spacing: 0.5px !important;
                line-height: 1.1 !important;
            }
            #stn1-loadcell-screen .cal-live-val {
                font-family: var(--font-mono) !important;
                font-size: 24px !important;
                font-weight: 900 !important;
                color: var(--tx) !important;
                line-height: 1.05 !important;
                white-space: nowrap !important;
            }
        `;
        document.head.appendChild(style);
    """)
    time.sleep(0.3)
    dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    driver.save_screenshot(f'{dir_p}\\test_999kg.png')
    im = Image.open(f'{dir_p}\\test_999kg.png')
    crop_card = im.crop((390, 75, 790, 175))
    crop_card.save(f'{dir_p}\\crop_test_999kg.png')
    print('Tested 999 kg successfully!')
finally:
    driver.quit()
