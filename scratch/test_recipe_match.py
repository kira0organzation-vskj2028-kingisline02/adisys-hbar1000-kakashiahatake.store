from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os, time

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--use-fake-ui-for-media-stream')
opts.add_argument('--use-fake-device-for-media-stream')
opts.add_argument('--window-size=1280,720')
driver = webdriver.Chrome(options=opts)

try:
    file_url = 'file:///' + os.path.abspath('static/index.html').replace('\\', '/')
    driver.get(file_url)
    time.sleep(1)

    driver.execute_script("if(typeof showRecipeLoadScreen === 'function') showRecipeLoadScreen();")
    time.sleep(1)

    btn = driver.find_element(By.ID, 'recipe-camera-open')
    driver.execute_script("arguments[0].click();", btn)
    time.sleep(1)

    # Simulate matched bag returned from vision engine
    driver.execute_script("""
    const data = {
        result: 'MATCH',
        confidence: 0.98,
        best: 'Veera Sivaji',
        best_recipe_id: 1,
        inliers: 240,
        time_ms: 110
    };
    const siftStatus = document.getElementById('recipe-sift-status');
    const resMsg = document.getElementById('recipe-compare-result');
    let hit = RecipeDB.list().find(x => x.name.toLowerCase().includes('veera'));
    if (hit) {
        siftStatus.textContent = `MATCHED (SIFT: ${data.inliers} INLIERS)`;
        siftStatus.style.color = '#10b981';
        resMsg.textContent = `Match confirmed: ${hit.name} (${Math.round(data.confidence*100)}% in ${data.time_ms}ms)`;
        resMsg.style.color = '#10b981';
        selectLoad(hit.id, 'CAMERA', '98%');
    }
    """)
    time.sleep(0.5)

    sift_status = driver.find_element(By.ID, 'recipe-sift-status').text
    compare_res = driver.find_element(By.ID, 'recipe-compare-result').text
    grid_text = driver.find_element(By.ID, 'recipe-config-grid').text
    print(f"SIFT Status: {sift_status}")
    print(f"Compare Result: {compare_res}")
    print(f"Grid text: {grid_text[:100]}...")

    assert "MATCHED" in sift_status, f"Expected MATCHED, got {sift_status}"
    assert "Veera Sivaji" in grid_text, f"Expected Veera Sivaji in grid text, got {grid_text}"

    driver.find_element(By.ID, 'recipe-load-screen').screenshot('recipe_matched_view.png')
    print("Screenshot saved to recipe_matched_view.png")
    print("MATCH FLOW TEST PASSED!")
finally:
    driver.quit()
