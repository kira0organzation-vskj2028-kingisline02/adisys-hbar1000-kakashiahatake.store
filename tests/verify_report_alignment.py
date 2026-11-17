import time, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1280,720')
driver = webdriver.Chrome(options=opts)

try:
    file_url = 'file:///' + os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(file_url)
    time.sleep(1)
    
    # Open report modal
    btn = driver.find_element(By.ID, 'btn-open-report')
    driver.execute_script('arguments[0].click();', btn)
    time.sleep(1)
    
    # Check bounding boxes of all report-metric elements
    metrics = driver.find_elements(By.CSS_SELECTOR, '.report-metric')
    print(f"Total metrics found: {len(metrics)}")
    assert len(metrics) == 9, f"Expected 9 metrics, got {len(metrics)}"
    
    boxes = []
    for i, m in enumerate(metrics):
        r = m.rect
        t = m.text.replace('\n', ' | ')
        boxes.append(r)
        print(f"Metric {i}: rect={r} | text={t}")
    
    # Check for any overlapping rectangles
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1 = boxes[i]
            b2 = boxes[j]
            # Check overlap: (x1 < x2 + w2) and (x1 + w1 > x2) and (y1 < y2 + h2) and (y1 + h1 > y2)
            # Add small tolerance of 0.5px for border touching
            tol = 0.5
            x_overlap = (b1['x'] < b2['x'] + b2['width'] - tol) and (b1['x'] + b1['width'] > b2['x'] + tol)
            y_overlap = (b1['y'] < b2['y'] + b2['height'] - tol) and (b1['y'] + b1['height'] > b2['y'] + tol)
            if x_overlap and y_overlap:
                overlaps.append((i, j, boxes[i], boxes[j]))
    
    assert len(overlaps) == 0, f"Detected overlapping metric boxes: {overlaps}"
    print("SUCCESS: Zero metric box overlaps detected!")
    
    # Take screenshot of the report screen
    rep = driver.find_element(By.ID, 'report-screen')
    ss_path = os.path.abspath('report_screen_native_fixed.png')
    rep.screenshot(ss_path)
    print(f"Saved screenshot: {ss_path}")
    
finally:
    driver.quit()
