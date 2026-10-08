@echo off
rem Opened by the "AFNI Command Prompt" shortcut: sets up the AFNI environment
rem (programs, scripts, tcsh, Python) for this window only and prints how to start.
call "%~dp0afni-env.cmd"
if errorlevel 1 exit /b 1
title AFNI Command Prompt
echo.
echo   AFNI command prompt
echo   -------------------
echo   AFNI programs and scripts run in this window. Try:
echo.
echo       3dinfo -help
echo       afni_proc.py -help
echo.
echo   Change to your data folder first (no spaces in the path), for example:
echo.
echo       cd /d C:\data\mri
echo.
echo   Write file names with forward slashes: 3dinfo C:/data/anat+orig
echo   In this window quote options with double quotes: "BLOCK(2,1)"
echo   Run a generated proc script with: tcsh -xef proc.subj
echo   For a tcsh prompt as on Linux, use the "AFNI Shell" shortcut.
echo.
echo   Help for every program: https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/
echo.
