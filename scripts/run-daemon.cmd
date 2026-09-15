@echo off
REM Manual starter only. This script does not create a scheduled task.
REM Set HARNESS_ROOT and ALLOWED_REPOSITORY before running.
set "HARNESS_ROOT=E:\work\project\.harness"
set "ALLOWED_REPOSITORY=E:\work\project"
cd /d "E:\python\prd-harness"
python -m prd_harness --root "%HARNESS_ROOT%" --allowed-repo "%ALLOWED_REPOSITORY%" --executor "python E:\python\prd-harness\scripts\agy_executor.py" daemon
