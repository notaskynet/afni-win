@echo off
rem Opened by the "AFNI Command Prompt" shortcut: puts this AFNI on PATH for
rem this window only and prints how to start.
set "PATH=%~dp0;%PATH%"
title AFNI Command Prompt
echo.
echo   AFNI command prompt
echo   -------------------
echo   AFNI programs run in this window. Try:
echo.
echo       3dinfo -help
echo       3dcalc -help
echo.
echo   Change to your data folder first, for example:
echo.
echo       cd /d C:\Users\%USERNAME%\Documents\mri
echo.
echo   In AFNI commands write file names with forward slashes:
echo       3dinfo C:/data/anat+orig
echo.
echo   Help for every program: https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/
echo.
