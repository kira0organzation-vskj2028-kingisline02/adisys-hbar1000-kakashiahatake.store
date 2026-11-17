from PIL import Image

im = Image.open(r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\loadcell_current.png')
print('Size:', im.size)

# Let's crop the whole stn1 cal modal
# The modal is typically in the center or occupies the screen
crop_full = im.crop((0, 0, im.size[0], im.size[1]))
crop_full.save(r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\crop_full_loadcell.png')
