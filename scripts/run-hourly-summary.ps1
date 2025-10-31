param(
    [string]
    C:\Users\meera\active-apps-monitor\scripts\..\app-usage.log = "C:\Users\meera\active-apps-monitor\scripts\..\app-usage.log",
    [string]
    C:\Users\meera\active-apps-monitor\scripts\..\usage-hourly.log = "C:\Users\meera\active-apps-monitor\scripts\..\usage-hourly.log",
    [string]
    C:\Users\meera\active-apps-monitor\scripts\..\.simple_hourly_state.json = "C:\Users\meera\active-apps-monitor\scripts\..\.simple_hourly_state.json"
)
python "C:\Users\meera\active-apps-monitor\simple_hourly.py" --logfile "C:\Users\meera\active-apps-monitor\scripts\..\app-usage.log" --out-log "C:\Users\meera\active-apps-monitor\scripts\..\usage-hourly.log" --append --state "C:\Users\meera\active-apps-monitor\scripts\..\.simple_hourly_state.json"
