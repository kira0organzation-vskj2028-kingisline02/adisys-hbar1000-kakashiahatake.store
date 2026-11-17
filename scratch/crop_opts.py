from PIL import Image

dir_p = r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4'

for opt in ['A', 'B', 'C']:
    im = Image.open(f'{dir_p}\\full_opt_{opt}.png')
    crop_card = im.crop((390, 75, 790, 175))
    crop_card.save(f'{dir_p}\\crop_card_{opt}.png')
    
    # Also crop the whole screen (0, 60, 800, 420)
    crop_screen = im.crop((0, 60, 800, 420))
    crop_screen.save(f'{dir_p}\\crop_screen_{opt}.png')
print('Cropped!')
