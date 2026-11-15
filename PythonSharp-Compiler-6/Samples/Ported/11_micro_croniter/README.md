# Ported: `11_micro_croniter`

A fast recurrence calculator for standard 5-part cron expressions, calendar modulo mathematics, and leap year traversal ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `croniter` library.

---

## Features

- **Standard 5-Field Cron Syntax**:
  - `minute` (0-59), `hour` (0-23), `day_of_month` (1-31), `month` (1-12), `day_of_week` (0-6 / 7 for Sunday)
  - Wildcards (`*`)
  - Value lists (`1,15,30`)
  - Ranges (`9-17`)
  - Step intervals (`*/15`, `1-10/2`)
- **Calendar & Time Calculations**:
  - Leap year detection (`IsLeapYear`) and days-in-month calculation (`DaysInMonth`)
  - Sakamoto's Gregorian day-of-week formula (`GetDayOfWeek`)
  - `CronDateTime` record with ISO-like string formatting
- **Scheduling**:
  - `GetNext()`: Advances minute-by-minute with rollover for minutes, hours, days, months, and leap years
  - `IsValid(expression)`: Syntax verification without throwing exceptions

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/11_micro_croniter -o Samples/Ported/11_micro_croniter/dist

# 2. Run the test harness
python3 Samples/Ported/11_micro_croniter/run_croniter.py
```

