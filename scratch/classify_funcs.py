import json
import re

with open("scratch/funcs_with_code.json", "r", encoding="utf-8") as f:
    funcs = json.load(f)

# Define classifications and logic
audited_funcs = []

for f in funcs:
    name = f['name']
    line = f['line']
    end_line = f['end_line']
    code = f['code_full']
    
    # Defaults
    classification = "KEEP in UI"
    reason = "Pure visual layout / DOM binding / event listener"
    endpoint = "None (Client visual/DOM)"

    # 1. STORAGE / JOB / CALIBRATION / PASSCODE / MATCHING / SIMULATION / MATH
    if name == 'startSimulatedSensors':
        classification = "MOVE to server"
        reason = "Generates virtual sensor telemetry and fake Modbus data in browser; belongs entirely in server.py (or modbus_slave_sim.py / FBARX_SIM=1)"
        endpoint = "POST /api/action { action: 'start_sim' } or server simulator thread"
    elif name in ['score', 'loadImage', 'sigFromDataUrl', 'signature']:
        classification = "MOVE to server"
        reason = "Browser-side image feature extraction and matching. Image matching and comparison belong in vision.py on the server"
        endpoint = "POST /api/camera/compare, POST /api/camera/match"
    elif name in ['startJob', 'endJob']:
        classification = "MOVE to server"
        reason = "Job lifecycle, timestamps, database persistence and active job state belong on server, not in browser memory or localStorage"
        endpoint = "POST /api/action { action: 'start_job' | 'end_job' }"
    elif name == 'updateJobUI':
        classification = "SPLIT"
        reason = "Render job state received from server (UI), but state retention and job timer/counter calculations move to server"
        endpoint = "GET /api/state"
    elif name == 'updateReportScreen':
        classification = "SPLIT"
        reason = "Rendering HTML report rows/tables stays in UI, but report aggregation, counts, percentages and banding calculations move to server"
        endpoint = "GET /api/report"
    elif name in ['reportGetRecords', 'reportFilteredRecords']:
        classification = "MOVE to server"
        reason = "Database querying, filtering by date/recipe/operator, and pagination belong in server SQLite query layer"
        endpoint = "GET /api/report?start=...&end=...&recipe=...&operator=..."
    elif name in ['toggleReportDateSort', 'updateReportSortUI']:
        classification = "KEEP in UI"
        reason = "UI sort indicators and client view sorting order of already retrieved report rows"
        endpoint = "None (UI view state)"
    elif name == 'populateReportDropdowns':
        classification = "SPLIT"
        reason = "Populating select elements is UI, but source lists of recipes and operators must come from server database"
        endpoint = "GET /api/recipes, GET /api/operators"
    elif name in ['exportReportXls', 'exportReportPdf', 'reportCsv']:
        classification = "SPLIT"
        reason = "File trigger/download in browser, but pre-calculated tabular summary and aggregations supplied by server"
        endpoint = "GET /api/report"
    elif name in ['reportEscape', 'downloadReportBlob', 'urlToDataUrl', 'reportNowLocalInputValue', 'reportFormatDate', 'getReportImages']:
        classification = "KEEP in UI"
        reason = "Helper utilities for report DOM formatting, blob download, and local time string conversion"
        endpoint = "None (Client helper)"
    elif name == 'bindReport':
        classification = "KEEP in UI"
        reason = "Event listeners for opening and closing the report screen modal"
        endpoint = "None (DOM events)"
    elif name == 'startClock':
        classification = "KEEP in UI"
        reason = "Visual topbar clock display formatting (local time hours:minutes:seconds)"
        endpoint = "None (Client visual clock)"
    elif name in ['returnToHomeScreen', 'bindNavigation']:
        classification = "KEEP in UI"
        reason = "Screen switching between #screen-stn, #screen-recipe, #screen-cam, etc."
        endpoint = "None (DOM view routing)"
    elif name == 'initRuler99Ticks':
        classification = "KEEP in UI"
        reason = "DOM creation of 99 ticks on visual ruler track"
        endpoint = "None (Client DOM rendering)"
    elif name == 'updateRepAndRulerDisplay':
        classification = "SPLIT"
        reason = "Ruler needle positioning is visual UI, but error calculation and repeat length actual validation move to server"
        endpoint = "GET /api/state"
    elif name == 'updateDynamicCounterBands':
        classification = "SPLIT"
        reason = "Renders counter badge DOM text, but banding partition rules, bin counts and totals move to server"
        endpoint = "GET /api/state"
    elif name == 'updateMarkWindowWithError':
        classification = "SPLIT"
        reason = "Renders mark window box UI, but mark window error limits and calculations move to server"
        endpoint = "GET /api/state"
    elif name == 'pollFBarXState':
        classification = "SPLIT"
        reason = "Single UI periodic state poll (200-500ms) that renders returned state. All decision-making and hardware interrogation stay in server.py"
        endpoint = "GET /api/state"
    elif name == 'setFbarxBanner':
        classification = "KEEP in UI"
        reason = "Renders top banner color and text depending on server state ('OK', 'DISCONNECTED', 'SIMULATED')"
        endpoint = "None (Client DOM rendering)"
    elif name == 'fbarxPost':
        classification = "MOVE to server"
        reason = "Replace direct hardware post endpoints with unified action dispatcher POST /api/action"
        endpoint = "POST /api/action"
    elif name in ['initSegmentTracks', 'updateSegmentTrack', 'normalizeOutput', 'formatOutput']:
        classification = "KEEP in UI"
        reason = "Visual bar graph / LED segment rendering and decimal string formatting"
        endpoint = "None (Client rendering)"
    elif name == 'bindModeButtons':
        classification = "SPLIT"
        reason = "Click handlers stay in UI, but mode change validation and sending action move to POST /api/action"
        endpoint = "POST /api/action { action: 'set_mode', station, mode }"
    elif name in ['updateCameraForStationModes', 'applyModeInteractionState']:
        classification = "KEEP in UI"
        reason = "Toggles UI button disabled/active classes and camera badge based on state received from server"
        endpoint = "GET /api/state"
    elif name in ['setEnabled', 'setGroup']:
        classification = "KEEP in UI"
        reason = "DOM utility helpers for enabling/disabling interactive button groups"
        endpoint = "None (DOM utility)"
    elif name in ['bindSteppers', 'setupStep', 'stepDown', 'stepUp']:
        classification = "SPLIT"
        reason = "UI click handlers for +/- steppers stay in UI, but clamp ranges and output stepping action move to server"
        endpoint = "POST /api/action { action: 'step_output', station, direction }"
    elif name == 'bindUnitToggle':
        classification = "SPLIT"
        reason = "Click handler in UI, but unit selection preference persists on server machine state"
        endpoint = "POST /api/action { action: 'set_unit', unit: 'KG'|'N' }"
    elif name in ['syncBrakeTypeUI', 'bindBrakeTypeSelectors']:
        classification = "SPLIT"
        reason = "Radio/button visual sync in UI, but brake type configuration persists on server"
        endpoint = "POST /api/action { action: 'set_brake_type' }"
    elif name in ['getStn1ControlValues', 'initStn1ControlDraft', 'discardStn1ControlDraft',
                  'getStn1LoadcellValues', 'initStn1LoadcellDraft', 'discardStn1LoadcellDraft',
                  'getStn2CalValues', 'initStn2CalDraft', 'discardStn2CalDraft']:
        classification = "SPLIT"
        reason = "Draft value holding in UI while modal is open, but initial loading and final saving move to server SQLite"
        endpoint = "GET/POST /api/calibration"
    elif name == 'bindStn1Calibration':
        classification = "KEEP in UI"
        reason = "Event listeners for opening STN 1 calibration modal"
        endpoint = "None (DOM events)"
    elif name in ['handleCalibrationConfirm', 'handleProtectedPasswordConfirm', 'checkProtectedPassword']:
        classification = "MOVE to server"
        reason = "Passcode verification ('1111', '2222', '3333', '4444') and unlock permission must happen strictly on server"
        endpoint = "POST /api/login or POST /api/action { action: 'verify_passcode' }"
    elif name in ['openCalibrationPad', 'openProtectedNumericPassword']:
        classification = "KEEP in UI"
        reason = "Opens visual on-screen numpad modal for user to type passcode"
        endpoint = "None (Modal UI trigger)"
    elif name in ['bindNumpadEngine', 'openNumpadModal', 'closeNumpadModal']:
        classification = "KEEP in UI"
        reason = "Touch keypad digit entry and backspace/cancel/clear visual handling"
        endpoint = "None (Virtual keyboard UI)"
    elif name in ['validateNumpadValue', 'handleNumpadConfirm']:
        classification = "MOVE to server"
        reason = "Value range validation, min/max limits, and saving validated value must be verified and enforced by server"
        endpoint = "POST /api/action { action: 'set_parameter', target, value }"
    elif name == 'updateErrorPercentageDisplay':
        classification = "SPLIT"
        reason = "Renders color and text of error percentage pill, but percentage math and pass/fail thresholds move to server"
        endpoint = "GET /api/state"
    elif name in ['runAutoCameraDetection', 'detectRecipeFromFrame']:
        classification = "MOVE to server"
        reason = "Camera snapshot analysis and matching against recipe database belong in vision.py on server"
        endpoint = "POST /api/camera/match"
    elif name in ['openLiveCam', 'startLiveCamera', 'stopLiveCamera']:
        classification = "SPLIT"
        reason = "Opening inspection UI modal and attaching <img> source stays in UI; starting/stopping camera thread and processing frames stay on server"
        endpoint = "POST /api/action { action: 'camera_start' | 'camera_stop' }"
    elif name in ['bindRulerZeroCalibration', 'bindRulerScaleCalibration']:
        classification = "SPLIT"
        reason = "UI calibration wizard buttons stay in UI; zero-offset calculation and px-per-mm line calibration move to server"
        endpoint = "POST /api/calibration"
    elif name in ['renderLiveAmmeters', 'renderLiveAmmeter', 'setNeedle', 'updateNeedles']:
        classification = "KEEP in UI"
        reason = "SVG needle angle math and DOM attribute rotation based on server-provided ammeter numbers"
        endpoint = "GET /api/state"
    elif 'modal' in name.lower() or 'popup' in name.lower() or 'dialog' in name.lower() or 'toast' in name.lower():
        classification = "KEEP in UI"
        reason = "Visual overlay display, dismissal, and animations"
        endpoint = "None (Client UI)"
    elif name.startswith('bind') or name.startswith('setup') or name.startswith('init'):
        classification = "KEEP in UI"
        reason = "DOM initialization and event listener attachment"
        endpoint = "None (Client initialization)"
    elif 'render' in name.lower() or 'update' in name.lower() or 'display' in name.lower() or 'format' in name.lower():
        classification = "KEEP in UI"
        reason = "DOM rendering of server-provided state"
        endpoint = "GET /api/state"
    
    audited_funcs.append({
        'name': name,
        'line': line,
        'end_line': end_line,
        'classification': classification,
        'reason': reason,
        'endpoint': endpoint
    })

with open("scratch/audited_functions.json", "w", encoding="utf-8") as out:
    json.dump(audited_funcs, out, indent=2)

print(f"Audited {len(audited_funcs)} functions.")
# Print breakdown
keep_count = sum(1 for x in audited_funcs if x['classification'] == 'KEEP in UI')
move_count = sum(1 for x in audited_funcs if x['classification'] == 'MOVE to server')
split_count = sum(1 for x in audited_funcs if x['classification'] == 'SPLIT')
print(f"Breakdown: KEEP in UI: {keep_count}, MOVE to server: {move_count}, SPLIT: {split_count}")
