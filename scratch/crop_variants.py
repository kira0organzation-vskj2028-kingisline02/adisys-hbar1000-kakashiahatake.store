from PIL import Image

dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'

for v in ['variant1_label_top', 'variant2_value_top', 'variant3_rows']:
    im = Image.open(f'{dir_p}\\{v}.png')
    # cal-zero-row bounding box: approx x from 400 to 790, y from 75 to 175
    crop = im.crop((390, 75, 790, 175))
    crop.save(f'{dir_p}\\crop_{v}.png')
    print(f'Cropped {v}')
