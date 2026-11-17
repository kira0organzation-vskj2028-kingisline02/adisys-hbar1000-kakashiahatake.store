import subprocess, time, sys, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TEST_PORT = 11299
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
    
    # 1. Test clicking camera box on Screen 0 to open camera inspection
    plate = driver.find_element('id', 'recipe-live-cam-plate')
    plate.click()
    time.sleep(1.5)
    
    res_screen2 = driver.execute_script('''
        const camScreen = document.getElementById('screen-cam');
        const isActive = camScreen ? camScreen.classList.contains('active') : false;
        const fullImg = document.getElementById('full-cam-preview-img');
        const fullVid = document.getElementById('full-cam-video');
        
        return {
            camScreenActive: isActive,
            fullImgSrc: fullImg ? fullImg.src : null,
            fullImgDisplay: fullImg ? getComputedStyle(fullImg).display : null,
            fullImgOpacity: fullImg ? getComputedStyle(fullImg).opacity : null,
            fullVidDisplay: fullVid ? getComputedStyle(fullVid).display : null
        };
    ''')
    print('Screen 2 Camera Inspection check:', res_screen2)
    assert res_screen2['camScreenActive'] == True
    assert '/api/camera/stream' in (res_screen2['fullImgSrc'] or '')
    assert res_screen2['fullImgDisplay'] == 'block'
    
    dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'
    driver.save_screenshot(f'{dir_p}\\verified_camera_screen2.png')
    print('Saved verified_camera_screen2.png')
    
    # 2. Return to home and test live feed on Screen 0
    driver.execute_script('''
        document.querySelectorAll('.screen-panel').forEach(p => p.classList.remove('active'));
        document.getElementById('screen-stn').classList.add('active');
        if (typeof window.applyServerStreamToAllViews === 'function') {
          window.applyServerStreamToAllViews();
        }
    ''')
    time.sleep(1.5)
    
    res_screen0 = driver.execute_script('''
        const homeImg = document.getElementById('recipe-live-cam-img');
        const homeVid = document.getElementById('home-cam-video');
        const offOverlay = document.getElementById('live-cam-off-overlay');
        const stat = document.getElementById('live-cam-top-stat')?.textContent;
        const ledColor = document.getElementById('live-cam-led')?.style?.background;
        
        return {
            homeImgSrc: homeImg ? homeImg.src : null,
            homeImgDisplay: homeImg ? getComputedStyle(homeImg).display : null,
            homeVidDisplay: homeVid ? getComputedStyle(homeVid).display : null,
            offOverlayDisplay: offOverlay ? getComputedStyle(offOverlay).display : null,
            stat: stat,
            ledColor: ledColor
        };
    ''')
    print('Screen 0 Camera View check:', res_screen0)
    assert '/api/camera/stream' in (res_screen0['homeImgSrc'] or '')
    assert res_screen0['homeImgDisplay'] == 'block'
    assert res_screen0['offOverlayDisplay'] == 'none'
    
    driver.save_screenshot(f'{dir_p}\\verified_camera_screen0.png')
    print('Saved verified_camera_screen0.png')
    print('ALL CAMERA TESTS PASSED!')
finally:
    driver.quit()
    server_proc.terminate()
    server_proc.wait(timeout=2)
