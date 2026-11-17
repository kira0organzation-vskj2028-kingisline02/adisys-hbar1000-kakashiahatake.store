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
    time.sleep(0.5)
    
    # Just show the dialog and update display via the native app functions
    driver.execute_script("""
        const scr = document.getElementById("stn1-cal-screen");
        if (scr) scr.classList.add("open");
        document.getElementById("stn1-password-screen").style.display = "none";
        document.getElementById("stn1-control-screen").style.display = "none";
        document.getElementById("stn1-loadcell-screen").style.display = "flex";
        if (typeof updateCalibrationDisplay === 'function') updateCalibrationDisplay();
    """)
    time.sleep(0.5)
    
    dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    out_file = f'{dir_p}\\loadcell_final_verified_800x480.png'
    driver.save_screenshot(out_file)
    
    im = Image.open(out_file)
    crop_card = im.crop((390, 75, 790, 175))
    crop_card.save(f'{dir_p}\\crop_card_final_verified.png')
    
    crop_screen = im.crop((0, 0, 800, 480))
    crop_screen.save(f'{dir_p}\\crop_screen_final_verified.png')
    print('Final verified screenshots captured!')
finally:
    driver.quit()
