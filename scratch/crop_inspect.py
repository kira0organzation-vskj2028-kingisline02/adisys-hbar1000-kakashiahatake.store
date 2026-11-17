from PIL import Image

im = Image.open(r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\loadcell_current.png')
print('Size:', im.size)

# Let's crop the cal-zero-row area
# In 782x328, let's find the bounding box
# Let's crop (350, 40, 750, 160)
crop1 = im.crop((350, 30, 750, 150))
crop1.save(r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\crop_current_zero_row.png')
print('Saved crop_current_zero_row.png')
