from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os, time

opts = Options()
opts.add_argument('--headless=new')
driver = webdriver.Chrome(options=opts)

file_url = 'file:///' + os.path.abspath('static/index.html').replace('\\', '/')
driver.get(file_url)

driver.execute_script("document.getElementById('recipe-load-screen').classList.add('open');")
time.sleep(0.5)

res = driver.execute_script("""
const v = document.getElementById('recipe-camera-video');
return {
    parent: v.parentElement.tagName,
    offsetParent: v.parentElement.offsetParent,
    offsetParentIsNull: (v.parentElement.offsetParent === null)
};
""")
print('Result:', res)
driver.quit()
