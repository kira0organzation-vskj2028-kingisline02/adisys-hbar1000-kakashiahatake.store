Passwords

Station / Calibration press → require a password (existing one is fine; keep similar behaviour).
Station 2 → password only.
Final Recipe 3 → password 3333.
Recipe 4 → password 4444.
(Previously used 1111 / 2222; apply the new ones only for calibrate entry.)

Station 1 / Calibration screen

Keep C1 : 0, A repeat 800, M2, C2 : 0.
C count value changes only from 0 to 99.
Weight + Signal share a common value (same place for both).
Place the Weight field with keypad below the existing fields (use the arrow mark already given).
Leave extra empty space for possible future use.

Powder / Pneumatic Brake

When Powder Brake is selected → enable the related value/condition.
When Numeric/Pneumatic is selected → keep it in disabled condition (so it does not appear suddenly).
Value should be settable only when Powder Brake is selected. Keep showing the last value; just prevent setting when not selected.

Break Type

Change Break Type to a radio-button style control (instead of normal key).
Label can simply be “Break Type” (remove or ignore the word “ratio”).

Image & Operator handling (Calibrate / Recipe)

Add 3 JPEG images (full clarity) for image selection.
Operators are common (not recipe-specific). Support multiple operators (3–5 or more) that can be selected/added.
Operator can be chosen by:
Name (combo / list)
Image scroll
Live camera (face / image compare)

On operator select → show the corresponding saved image.
Scrolling images should also update the related parameters.
Open Camera + Read + Compare buttons already present; keep the flow.
After capture → Preview + Confirm to Load.
Remove or simplify Save & Exit / Home behaviour:
This screen is mainly for selection/load (no real editing of existing recipe data).
Confirm & Load → load the selected data.
Home → go back without loading new data (or keep old data).


Database & Loading

Connect database.
Load the 3 images + their parameters (you can put random values for Mark Sensor etc. for now).
Save operators once (independent of recipe).
When a recipe is selected → pull the saved operator list and images from DB.
After load → Main/Home page should show:
Selected image
Parameters
Live camera feed on the right side

Image comparison / displacement calculation → next phase (not required now).

Report side

Start Time → set when the recipe is loaded.
End Time → set when the next job starts (becomes start time of the new job).
Export to Excel → include Image Name + Operator Name.
Prefer embedding / showing the actual image in the report (helps identification even if names are similar).

Delivery / Technical

Prefer an executable (so it runs cleanly; backend/Python still needed for DB).
All libraries should link correctly; normal desktop app open should load the interface.
First phase = current UI fixes + passwords + DB connectivity + image/operator load + basic home-page display.
Second phase = front + back image comparison + displacement/error calculation (target ~0.1 mm if possible, acceptable ±5 mm or up to 40 mm max for now).
Third phase = fine-tuning, video logging, help files, etc.