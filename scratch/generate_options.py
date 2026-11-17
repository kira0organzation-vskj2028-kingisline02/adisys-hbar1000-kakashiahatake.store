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
    """)
    
    # OPTION A: 2 Columns, label on top, value below
    driver.execute_script("""
        const calInfo = document.querySelector("#stn1-loadcell-screen .cal-zero-row .cal-info");
        calInfo.innerHTML = `
            <div class="cal-live-item">
                <span class="cal-live-label">WEIGHT</span>
                <b class="cal-live-val" id="cal-knownWeight">0 kg</b>
            </div>
            <div class="cal-live-item">
                <span class="cal-live-label">SIGNAL</span>
                <b class="cal-live-val">±4.0 mV</b>
            </div>
        `;
        calInfo.style.cssText = `
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 12px !important;
            padding: 8px 14px !important;
            align-items: center !important;
            box-sizing: border-box !important;
            background: var(--panel) !important;
            border: 1px solid var(--border) !important;
            border-radius: 5px !important;
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
    driver.save_screenshot(f'{dir_p}\\full_opt_A.png')
    
    # OPTION C: 2 Columns, value on top, label below (matching field instrument)
    driver.execute_script("""
        const calInfo = document.querySelector("#stn1-loadcell-screen .cal-zero-row .cal-info");
        calInfo.innerHTML = `
            <div class="cal-live-item">
                <b class="cal-live-val" id="cal-knownWeight">0 kg</b>
                <span class="cal-live-label">WEIGHT</span>
            </div>
            <div class="cal-live-item">
                <b class="cal-live-val">±4.0 mV</b>
                <span class="cal-live-label">SIGNAL</span>
            </div>
        `;
    """)
    time.sleep(0.3)
    driver.save_screenshot(f'{dir_p}\\full_opt_C.png')

    # OPTION B: 2 rows (table/flex row style)
    driver.execute_script("""
        const calInfo = document.querySelector("#stn1-loadcell-screen .cal-zero-row .cal-info");
        calInfo.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:baseline; width:100%;">
                <span style="font-size:12px; font-weight:700; color:var(--tx-dim); letter-spacing:0.5px;">WEIGHT</span>
                <b id="cal-knownWeight" style="font-size:22px; font-weight:900; color:var(--tx);">0 kg</b>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; width:100%;">
                <span style="font-size:12px; font-weight:700; color:var(--tx-dim); letter-spacing:0.5px;">SIGNAL</span>
                <b style="font-size:22px; font-weight:900; color:var(--tx);">±4.0 mV</b>
            </div>
        `;
        calInfo.style.cssText = `
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            gap: 6px !important;
            padding: 8px 16px !important;
            box-sizing: border-box !important;
            background: var(--panel) !important;
            border: 1px solid var(--border) !important;
            border-radius: 5px !important;
        `;
    """)
    time.sleep(0.3)
    driver.save_screenshot(f'{dir_p}\\full_opt_B.png')
    print('Generated all 3 options full!')
finally:
    driver.quit()
